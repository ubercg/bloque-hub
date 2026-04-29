"""REST API for spaces, relationships, availability and booking rules."""

import uuid
from datetime import date
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from fastapi.exceptions import HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import (
    assert_space_mutable_by_requester,
    optional_tenant_for_catalog,
    require_superadmin,
    require_tenant,
    resolve_staff_space_tenant_id,
)
from app.modules.booking.models import Reservation, ReservationStatus
from app.modules.identity.models import User
from app.modules.inventory.models import Inventory, SlotStatus, Space, SpaceBookingRule, SpaceRelationship
from app.core.config import settings
from app.modules.inventory.schemas import (
    BlockSlotRequest,
    CheckAvailabilityGroupRequest,
    CheckAvailabilityGroupResponse,
    CheckAvailabilityRequest,
    CheckAvailabilityResponse,
    MonthAvailabilityResponse,
    SpaceBookingRuleRead,
    SpaceBookingRuleUpsert,
    SpaceCreate,
    SpacePromoMediaUploadResponse,
    SpaceRead,
    SpaceRelationshipCreate,
    SpaceRelationshipRead,
    SpaceUpdate,
    SlotRead,
    OccupancySlotRead,
    OccupancyStatus,
)
from app.modules.inventory.services import (
    block_child_and_parent,
    block_parent_and_children,
    check_group_availability,
    check_single_availability,
    get_month_availability,
    would_create_cycle,
)

router = APIRouter(prefix="/api", tags=["inventory"])

ALLOWED_OCCUPANCY_ROLES = {"COMMERCIAL", "OPERATIONS", "FINANCE", "SUPERADMIN"}

# Subida de imágenes promo (catálogo): PNG/JPEG/WebP/GIF, max configurado en settings.
_ALLOWED_PROMO_CT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
_SUFFIX_PROMO = {".jpg": ".jpg", ".jpeg": ".jpg", ".png": ".png", ".webp": ".webp", ".gif": ".gif"}


def _space_promo_extension(file: UploadFile) -> str:
    ct = (file.content_type or "").strip().lower()
    if ct in _ALLOWED_PROMO_CT:
        return _ALLOWED_PROMO_CT[ct]
    suf = Path(file.filename or "").suffix.lower()
    if suf in _SUFFIX_PROMO:
        return _SUFFIX_PROMO[suf]
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Tipos permitidos: JPEG, PNG, WebP, GIF",
    )


def _require_occupancy_role(role: str | None) -> None:
    if role not in ALLOWED_OCCUPANCY_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient role for occupancy monitor",
        )


def _map_occupancy_status(slot_state: str, reservation_status: str | None) -> OccupancyStatus:
    if reservation_status in {ReservationStatus.CONFIRMED.value, "COMPLETED"}:
        return OccupancyStatus.CONFIRMED
    if slot_state == "RESERVED":
        return OccupancyStatus.CONFIRMED
    if slot_state == "AVAILABLE":
        return OccupancyStatus.AVAILABLE
    return OccupancyStatus.TENTATIVE


# ----- Spaces CRUD -----


@router.get("/spaces", response_model=list[SpaceRead])
def list_spaces(
    tenant_info: tuple[UUID, str | None] = Depends(optional_tenant_for_catalog),
    db: Session = Depends(get_db),
):
    """List spaces for the resolved tenant (JWT, sede query, o SUPERADMIN + ?tenant_id=).

    Filtro explícito por tenant_id: con rol SUPERADMIN RLS no acota SELECT; así el listado
    respeta la sede elegida (incl. override por query).
    """
    tenant_id, _role = tenant_info
    return db.query(Space).filter(Space.tenant_id == tenant_id).all()


@router.get("/spaces/{space_id}", response_model=SpaceRead)
def get_space(
    space_id: UUID,
    _: tuple[UUID, str | None] = Depends(optional_tenant_for_catalog),
    db: Session = Depends(get_db),
):
    """Get one space by id."""
    space = db.query(Space).filter(Space.id == space_id).first()
    if space is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found")
    return space


@router.post("/spaces", response_model=SpaceRead, status_code=status.HTTP_201_CREATED)
def create_space(
    request: Request,
    body: SpaceCreate,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
    tenant_id: UUID = Depends(resolve_staff_space_tenant_id),
):
    """Create a space. Staff usa su tenant; SUPERADMIN puede `?tenant_id=` para otra sede."""
    space = Space(tenant_id=tenant_id, **body.model_dump())
    db.add(space)
    db.commit()
    db.refresh(space)
    return space


@router.post(
    "/spaces/promo-media/upload",
    response_model=SpacePromoMediaUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_space_promo_media(
    file: UploadFile = File(...),
    _: tuple[UUID, str | None] = Depends(require_tenant),
    tenant_id: UUID = Depends(resolve_staff_space_tenant_id),
):
    """
    Sube una imagen para hero o galería del catálogo. Devuelve una URL pública (`/api/media/space-promo/...`).
    Misma regla de sede que POST /api/spaces: staff usa su tenant; SUPERADMIN puede `?tenant_id=`.
    """
    ext = _space_promo_extension(file)
    raw = file.file.read()
    if len(raw) > settings.MAX_SPACE_PROMO_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Archivo demasiado grande; máximo {settings.MAX_SPACE_PROMO_IMAGE_BYTES // (1024 * 1024)} MB",
        )
    if len(raw) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archivo vacío")

    safe_name = f"{uuid.uuid4().hex}{ext}"
    dest_dir = Path(settings.SPACE_PROMO_MEDIA_PATH) / str(tenant_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / safe_name
    dest_path.write_bytes(raw)

    public_url = f"/api/media/space-promo/{tenant_id}/{safe_name}"
    return SpacePromoMediaUploadResponse(url=public_url)


@router.patch("/spaces/{space_id}", response_model=SpaceRead)
def update_space(
    request: Request,
    space_id: UUID,
    body: SpaceUpdate,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Update a space (partial). SUPERADMIN puede editar cualquier espacio."""
    space = db.query(Space).filter(Space.id == space_id).first()
    if space is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found")
    assert_space_mutable_by_requester(request, space.tenant_id)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(space, k, v)
    db.commit()
    db.refresh(space)
    return space


@router.delete("/spaces/{space_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_space(
    request: Request,
    space_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Delete a space. SUPERADMIN puede borrar en cualquier tenant."""
    space = db.query(Space).filter(Space.id == space_id).first()
    if space is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found")
    assert_space_mutable_by_requester(request, space.tenant_id)
    db.delete(space)
    db.commit()


# ----- Relationships -----


@router.get("/space-relationships", response_model=list[SpaceRelationshipRead])
def list_relationships(
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """List space relationships for the current tenant."""
    return db.query(SpaceRelationship).all()


@router.post(
    "/space-relationships",
    response_model=SpaceRelationshipRead,
    status_code=status.HTTP_201_CREATED,
)
def create_relationship(
    request: Request,
    body: SpaceRelationshipCreate,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Create a parent-child relationship. Returns 400 if it would create a cycle."""
    tenant_id = request.state.tenant_id
    if would_create_cycle(
        tenant_id, body.parent_space_id, body.child_space_id, db
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This relationship would create a circular hierarchy",
        )
    rel = SpaceRelationship(
        tenant_id=tenant_id,
        parent_space_id=body.parent_space_id,
        child_space_id=body.child_space_id,
        relationship_type=body.relationship_type,
    )
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return rel


@router.delete(
    "/space-relationships/{relationship_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_relationship(
    relationship_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Delete a space relationship."""
    rel = db.query(SpaceRelationship).filter(SpaceRelationship.id == relationship_id).first()
    if rel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relationship not found",
        )
    db.delete(rel)
    db.commit()


# ----- Availability -----


@router.get("/spaces/{space_id}/availability")
def get_availability(
    space_id: UUID,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    auth: tuple[UUID, str | None] = Depends(optional_tenant_for_catalog),
    db: Session = Depends(get_db),
):
    """Return inventory slots (date range) or monthly calendar view.

    - With month=YYYY-MM: returns MonthAvailabilityResponse (calendar view CA-01).
    - With fecha_desde + fecha_hasta: returns list[SlotRead] (raw slots, legacy).
    """
    _, role = auth

    if month:
        parts = month.split("-")
        year, m = int(parts[0]), int(parts[1])
        return get_month_availability(space_id, year, m, db, role)

    if fecha_desde is None or fecha_hasta is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide month=YYYY-MM or both fecha_desde and fecha_hasta",
        )
    rows = (
        db.query(Inventory)
        .filter(
            Inventory.space_id == space_id,
            Inventory.fecha >= fecha_desde,
            Inventory.fecha <= fecha_hasta,
        )
        .order_by(Inventory.fecha, Inventory.hora_inicio)
        .all()
    )
    return rows


# ----- Check Availability (FR-03) -----


@router.post("/spaces/check-availability", response_model=CheckAvailabilityResponse)
def check_availability(
    body: CheckAvailabilityRequest,
    auth: tuple[UUID, str | None] = Depends(optional_tenant_for_catalog),
    db: Session = Depends(get_db),
):
    """Verify availability for a single slot (CA-02)."""
    _, role = auth
    return check_single_availability(
        space_id=body.espacio_id,
        fecha=body.fecha,
        hora_inicio=body.hora_inicio,
        hora_fin=body.hora_fin,
        db=db,
        role=role,
    )


@router.post("/spaces/check-availability-group", response_model=CheckAvailabilityGroupResponse)
def check_availability_group(
    body: CheckAvailabilityGroupRequest,
    auth: tuple[UUID, str | None] = Depends(optional_tenant_for_catalog),
    db: Session = Depends(get_db),
):
    """Verify availability for a group of slots (CA-03, used by EventCart)."""
    _, role = auth
    items = [
        {
            "espacio_id": item.espacio_id,
            "fecha": item.fecha,
            "hora_inicio": item.hora_inicio,
            "hora_fin": item.hora_fin,
        }
        for item in body.items
    ]
    return check_group_availability(items, db, role)


@router.get("/admin/occupancy", response_model=list[OccupancySlotRead])
def get_admin_occupancy(
    fecha_desde: date = Query(..., description="Fecha inicial (YYYY-MM-DD)"),
    fecha_hasta: date = Query(..., description="Fecha final (YYYY-MM-DD)"),
    estado: OccupancyStatus | None = Query(None, description="AVAILABLE|TENTATIVE|CONFIRMED"),
    space_id: UUID | None = Query(None, description="Filtrar por espacio"),
    db: Session = Depends(get_db),
    tenant_data: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Occupancy monitor for staff: slots by day/space with event and customer context."""
    tenant_id, role = tenant_data
    _require_occupancy_role(role)
    if fecha_hasta < fecha_desde:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="fecha_hasta must be greater or equal than fecha_desde",
        )

    query = (
        db.query(Inventory, Space, Reservation, User)
        .join(Space, Space.id == Inventory.space_id)
        .outerjoin(Reservation, Reservation.id == Inventory.reservation_id)
        .outerjoin(User, User.id == Reservation.user_id)
        .filter(
            Inventory.tenant_id == tenant_id,
            Inventory.fecha >= fecha_desde,
            Inventory.fecha <= fecha_hasta,
        )
        .order_by(Inventory.fecha.asc(), Inventory.hora_inicio.asc(), Space.name.asc())
    )
    if space_id is not None:
        query = query.filter(Inventory.space_id == space_id)

    rows = query.all()
    relationships = (
        db.query(SpaceRelationship)
        .filter(SpaceRelationship.tenant_id == tenant_id)
        .all()
    )
    parent_by_child: dict[UUID, list[UUID]] = {}
    children_by_parent: dict[UUID, list[UUID]] = {}
    for rel in relationships:
        parent_by_child.setdefault(rel.child_space_id, []).append(rel.parent_space_id)
        children_by_parent.setdefault(rel.parent_space_id, []).append(rel.child_space_id)

    space_name_by_id: dict[UUID, str] = {}
    slot_index: dict[tuple[UUID, date, object, object], tuple[Reservation | None, User | None]] = {}
    for inv, space, reservation, user in rows:
        space_name_by_id[space.id] = space.name
        slot_index[(inv.space_id, inv.fecha, inv.hora_inicio, inv.hora_fin)] = (reservation, user)

    out: list[OccupancySlotRead] = []
    for inv, space, reservation, user in rows:
        reservation_status = reservation.status.value if reservation else None
        occupancy = _map_occupancy_status(inv.estado.value, reservation_status)

        related_space_name: str | None = None
        related_event_name: str | None = None
        related_customer_name: str | None = None

        if reservation is None and inv.estado in {SlotStatus.BLOCKED_BY_PARENT, SlotStatus.BLOCKED_BY_CHILD}:
            related_ids = (
                parent_by_child.get(inv.space_id, [])
                if inv.estado == SlotStatus.BLOCKED_BY_PARENT
                else children_by_parent.get(inv.space_id, [])
            )
            for related_space_id in related_ids:
                rel_reservation, rel_user = slot_index.get(
                    (related_space_id, inv.fecha, inv.hora_inicio, inv.hora_fin),
                    (None, None),
                )
                if rel_reservation is not None:
                    related_space_name = space_name_by_id.get(related_space_id)
                    related_event_name = rel_reservation.event_name
                    related_customer_name = rel_user.full_name if rel_user else None
                    if rel_reservation.status in {ReservationStatus.CONFIRMED, ReservationStatus.COMPLETED}:
                        occupancy = OccupancyStatus.CONFIRMED
                    else:
                        occupancy = OccupancyStatus.TENTATIVE
                    break
            if related_space_name is None and related_ids:
                related_space_name = space_name_by_id.get(related_ids[0])

        if estado is not None and occupancy != estado:
            continue
        start_minutes = inv.hora_inicio.hour * 60 + inv.hora_inicio.minute
        end_minutes = inv.hora_fin.hour * 60 + inv.hora_fin.minute
        duration = max(0, end_minutes - start_minutes) / 60
        out.append(
            OccupancySlotRead(
                slot_id=inv.id,
                fecha=inv.fecha,
                hora_inicio=inv.hora_inicio,
                hora_fin=inv.hora_fin,
                duracion_horas=duration,
                space_id=space.id,
                space_name=space.name,
                slot_status=inv.estado,
                occupancy_status=occupancy,
                reservation_id=reservation.id if reservation else None,
                group_event_id=reservation.group_event_id if reservation else None,
                event_name=reservation.event_name if reservation else None,
                reservation_status=reservation_status,
                customer_name=(user.full_name if user else None),
                customer_email=(user.email if user else None),
                related_space_name=related_space_name,
                related_event_name=related_event_name,
                related_customer_name=related_customer_name,
            )
        )
    return out


# ----- Space Booking Rules CRUD (SuperAdmin) -----


@router.get("/space-booking-rules", response_model=list[SpaceBookingRuleRead])
def list_booking_rules(
    db: Session = Depends(get_db),
    _: None = Depends(require_superadmin),
):
    """List all booking rules (filtered by tenant via RLS)."""
    return db.query(SpaceBookingRule).all()


@router.get("/space-booking-rules/{space_id}", response_model=SpaceBookingRuleRead)
def get_booking_rule(
    space_id: UUID,
    db: Session = Depends(get_db),
    _: None = Depends(require_superadmin),
):
    """Get booking rule for a space."""
    rule = db.query(SpaceBookingRule).filter(SpaceBookingRule.space_id == space_id).first()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking rule not found")
    return rule


@router.put("/space-booking-rules/{space_id}", response_model=SpaceBookingRuleRead)
def upsert_booking_rule(
    request: Request,
    space_id: UUID,
    body: SpaceBookingRuleUpsert,
    db: Session = Depends(get_db),
    _: None = Depends(require_superadmin),
):
    """Create or update booking rule for a space (upsert)."""
    tenant_id = request.state.tenant_id
    rule = db.query(SpaceBookingRule).filter(SpaceBookingRule.space_id == space_id).first()
    if rule is None:
        rule = SpaceBookingRule(
            space_id=space_id,
            tenant_id=tenant_id,
            min_duration_minutes=body.min_duration_minutes,
            allowed_start_times=body.allowed_start_times,
        )
        db.add(rule)
    else:
        rule.min_duration_minutes = body.min_duration_minutes
        rule.allowed_start_times = body.allowed_start_times
    db.commit()
    db.refresh(rule)
    return rule


# ----- Block (internal / testing) -----


@router.post("/spaces/{space_id}/block", status_code=status.HTTP_204_NO_CONTENT)
def block_slot(
    request: Request,
    space_id: UUID,
    body: BlockSlotRequest,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Block a slot hierarchically: as_parent blocks parent + children; as_child blocks child + parent."""
    tenant_id = request.state.tenant_id
    if body.as_parent:
        block_parent_and_children(
            space_id, tenant_id,
            body.fecha, body.hora_inicio, body.hora_fin,
            db,
        )
    else:
        block_child_and_parent(
            space_id, tenant_id,
            body.fecha, body.hora_inicio, body.hora_fin,
            db,
        )
    db.commit()
