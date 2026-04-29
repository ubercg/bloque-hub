"""REST API for service orders (fulfillment)."""

from pathlib import Path
from uuid import UUID

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.exceptions import HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.db.session import get_db
from app.dependencies.auth import (
    require_evidence_upload,
    require_operations_or_admin,
    require_tenant,
)
from app.modules.booking.models import Reservation
from app.modules.fulfillment.models import (
    Checklist,
    EvidenceRequirement,
    EvidenceStatus,
    MasterServiceOrder,
    MasterServiceOrderStatus,
    ServiceOrderItem,
    ServiceOrderItemStatus,
)
from app.modules.fulfillment.schemas import (
    EvidenceRequirementRead,
    EvidenceRequirementReview,
    MasterServiceOrderRead,
    MasterServiceOrderStatusUpdate,
    ReadinessRead,
    ServiceOrderIdRead,
    ServiceOrderItemRead,
    ServiceOrderItemStatusUpdate,
)
from app.modules.fulfillment.services import compute_readiness, get_readiness

router = APIRouter(prefix="/api", tags=["fulfillment"])


def _get_order_or_404(order_id: UUID, tenant_id: UUID, db: Session) -> MasterServiceOrder:
    order = (
        db.query(MasterServiceOrder)
        .filter(
            MasterServiceOrder.id == order_id,
            MasterServiceOrder.tenant_id == tenant_id,
        )
        .first()
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service order not found")
    return order


def _get_item_or_404(item_id: UUID, tenant_id: UUID, db: Session) -> ServiceOrderItem:
    item = (
        db.query(ServiceOrderItem)
        .join(ServiceOrderItem.checklist)
        .join(Checklist.master_service_order)
        .filter(
            ServiceOrderItem.id == item_id,
            MasterServiceOrder.tenant_id == tenant_id,
        )
        .first()
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service order item not found")
    return item


ALLOWED_EVIDENCE_CONTENT_TYPES = {"application/pdf", "image/jpeg", "image/png"}
ALLOWED_EVIDENCE_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
MAX_EVIDENCE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


def _get_evidence_or_404(evidence_id: UUID, tenant_id: UUID, db: Session) -> EvidenceRequirement:
    ev = (
        db.query(EvidenceRequirement)
        .join(EvidenceRequirement.master_service_order)
        .filter(
            EvidenceRequirement.id == evidence_id,
            MasterServiceOrder.tenant_id == tenant_id,
        )
        .first()
    )
    if ev is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence requirement not found")
    return ev


def _get_order_by_reservation_for_customer(
    request: Request, reservation_id: UUID, tenant_id: UUID, db: Session
) -> MasterServiceOrder:
    """Get service order by reservation_id; 403 if reservation is not owned by current user."""
    reservation = db.query(Reservation).filter(
        Reservation.id == reservation_id,
        Reservation.tenant_id == tenant_id,
    ).first()
    if reservation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found")
    user_id = getattr(request.state, "user_id", None)
    if user_id is None or reservation.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this reservation",
        )
    return _get_order_by_reservation_staff(reservation_id, tenant_id, db)


def _get_order_by_reservation_staff(reservation_id: UUID, tenant_id: UUID, db: Session) -> MasterServiceOrder:
    """Get service order by reservation_id + tenant_id (no user check). For staff or after customer check."""
    order = (
        db.query(MasterServiceOrder)
        .filter(
            MasterServiceOrder.reservation_id == reservation_id,
            MasterServiceOrder.tenant_id == tenant_id,
        )
        .first()
    )
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No service order found for this reservation yet",
        )
    return order


@router.get("/service-orders", response_model=list[MasterServiceOrderRead])
def list_service_orders(
    request: Request,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """List service orders for the current tenant."""
    tenant_id = request.state.tenant_id
    orders = (
        db.query(MasterServiceOrder)
        .options(
            joinedload(MasterServiceOrder.checklists).joinedload(Checklist.items),
        )
        .filter(MasterServiceOrder.tenant_id == tenant_id)
        .order_by(MasterServiceOrder.created_at.desc())
        .all()
    )
    return orders


@router.get("/service-orders/{order_id}", response_model=MasterServiceOrderRead)
def get_service_order(
    request: Request,
    order_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Get one service order by id."""
    tenant_id = request.state.tenant_id
    order = (
        db.query(MasterServiceOrder)
        .options(
            joinedload(MasterServiceOrder.checklists).joinedload(Checklist.items),
        )
        .filter(
            MasterServiceOrder.id == order_id,
            MasterServiceOrder.tenant_id == tenant_id,
        )
        .first()
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service order not found")
    return order


@router.patch("/service-orders/{order_id}", response_model=MasterServiceOrderRead)
def patch_service_order(
    request: Request,
    order_id: UUID,
    body: MasterServiceOrderStatusUpdate,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
    __: None = Depends(require_operations_or_admin),
):
    """Update service order status. Requires OPERATIONS or SUPERADMIN."""
    tenant_id = request.state.tenant_id
    order = _get_order_or_404(order_id, tenant_id, db)
    order.status = body.status
    db.commit()
    order = (
        db.query(MasterServiceOrder)
        .options(
            joinedload(MasterServiceOrder.checklists).joinedload(Checklist.items),
        )
        .where(MasterServiceOrder.id == order_id)
        .first()
    )
    return order


@router.patch("/service-order-items/{item_id}", response_model=ServiceOrderItemRead)
def patch_service_order_item(
    request: Request,
    item_id: UUID,
    body: ServiceOrderItemStatusUpdate,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
    __: None = Depends(require_operations_or_admin),
):
    """Update service order item status (e.g. mark COMPLETED). Requires OPERATIONS or SUPERADMIN."""
    tenant_id = request.state.tenant_id
    item = _get_item_or_404(item_id, tenant_id, db)
    item.status = body.status
    if body.status == ServiceOrderItemStatus.COMPLETED:
        item.completed_at = datetime.now(timezone.utc)
    else:
        item.completed_at = None
    db.commit()
    db.refresh(item)
    # Re-evaluate readiness; may transition OS to READY
    compute_readiness(item.checklist.master_service_order_id, db)
    db.commit()
    return item


@router.get("/service-orders/{order_id}/readiness", response_model=ReadinessRead)
def get_order_readiness(
    request: Request,
    order_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Get readiness state for a service order (checklist + evidence). Used by Gate of Security."""
    tenant_id = request.state.tenant_id
    _get_order_or_404(order_id, tenant_id, db)
    result = get_readiness(order_id, db)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service order not found")
    is_ready, checklist_pct, evidence_complete, details = result
    return ReadinessRead(
        is_ready=is_ready,
        checklist_pct=checklist_pct,
        evidence_complete=evidence_complete,
        details=details,
    )


# ---------- Evidence (Buzón de Evidencias) ----------


@router.post(
    "/service-orders/{order_id}/evidence",
    response_model=EvidenceRequirementRead,
    status_code=status.HTTP_201_CREATED,
)
def upload_evidence(
    request: Request,
    order_id: UUID,
    tipo_documento: str = Form(..., description="e.g. INE_RESPONSABLE, CARTA_RESPONSIVA"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
    __: None = Depends(require_evidence_upload),
):
    """Upload a document for an evidence requirement. Allowed: PDF, JPG, PNG; max 10 MB."""
    tenant_id = request.state.tenant_id
    order = _get_order_or_404(order_id, tenant_id, db)
    content_type = (file.content_type or "").strip().lower()
    suffix = Path(file.filename or "").suffix.lower()
    if content_type not in ALLOWED_EVIDENCE_CONTENT_TYPES and suffix not in ALLOWED_EVIDENCE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Allowed types: PDF, JPG, PNG",
        )
    content = file.file.read()
    if len(content) > MAX_EVIDENCE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large; max 10 MB",
        )
    evidence = (
        db.query(EvidenceRequirement)
        .filter(
            EvidenceRequirement.master_service_order_id == order_id,
            EvidenceRequirement.tenant_id == tenant_id,
            EvidenceRequirement.tipo_documento == tipo_documento,
        )
        .first()
    )
    if not evidence:
        evidence = EvidenceRequirement(
            tenant_id=tenant_id,
            master_service_order_id=order_id,
            tipo_documento=tipo_documento,
            estado=EvidenceStatus.PENDIENTE,
            plazo_vence_at=datetime.now(timezone.utc),
        )
        db.add(evidence)
        db.flush()
    ext = suffix if suffix in ALLOWED_EVIDENCE_EXTENSIONS else ".pdf"
    storage = Path(settings.EVIDENCE_STORAGE_PATH)
    storage.mkdir(parents=True, exist_ok=True)
    safe_name = f"{evidence.id}{ext}"
    full_path = storage / safe_name
    full_path.write_bytes(content)
    evidence.file_path = safe_name  # relative to EVIDENCE_STORAGE_PATH
    evidence.filename = file.filename or safe_name
    evidence.file_size_bytes = len(content)
    evidence.estado = EvidenceStatus.PENDIENTE_REVISION
    evidence.uploaded_at = datetime.now(timezone.utc)
    evidence.intentos_carga = (evidence.intentos_carga or 0) + 1
    db.commit()
    db.refresh(evidence)
    return evidence


@router.get("/service-orders/{order_id}/evidence", response_model=list[EvidenceRequirementRead])
def list_evidence(
    request: Request,
    order_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """List evidence requirements for a service order."""
    tenant_id = request.state.tenant_id
    _get_order_or_404(order_id, tenant_id, db)
    items = (
        db.query(EvidenceRequirement)
        .filter(
            EvidenceRequirement.master_service_order_id == order_id,
            EvidenceRequirement.tenant_id == tenant_id,
        )
        .all()
    )
    return items


# ---------- Evidence by reservation (portal del cliente) ----------


@router.get(
    "/reservations/{reservation_id}/service-order",
    response_model=ServiceOrderIdRead,
)
def get_service_order_by_reservation(
    request: Request,
    reservation_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
    __: None = Depends(require_operations_or_admin),
):
    """Get service order id for a reservation. OPERATIONS/SUPERADMIN only (for evidence review)."""
    tenant_id = request.state.tenant_id
    order = _get_order_by_reservation_staff(reservation_id, tenant_id, db)
    return ServiceOrderIdRead(id=order.id)


@router.get(
    "/reservations/{reservation_id}/evidence-requirements",
    response_model=list[EvidenceRequirementRead],
)
def list_evidence_requirements_by_reservation(
    request: Request,
    reservation_id: UUID,
    db: Session = Depends(get_db),
    tenant_data: tuple[UUID, str | None] = Depends(require_tenant),
):
    """List evidence requirements for the service order linked to this reservation. Customer: own reservation only. OPERATIONS/SUPERADMIN: any reservation."""
    tenant_id, role = tenant_data
    if role in ("OPERATIONS", "SUPERADMIN"):
        order = _get_order_by_reservation_staff(reservation_id, tenant_id, db)
    else:
        order = _get_order_by_reservation_for_customer(request, reservation_id, tenant_id, db)
    items = (
        db.query(EvidenceRequirement)
        .filter(
            EvidenceRequirement.master_service_order_id == order.id,
            EvidenceRequirement.tenant_id == tenant_id,
        )
        .all()
    )
    return items


@router.post(
    "/reservations/{reservation_id}/evidence",
    response_model=EvidenceRequirementRead,
    status_code=status.HTTP_201_CREATED,
)
def upload_evidence_by_reservation(
    request: Request,
    reservation_id: UUID,
    tipo_documento: str = Form(..., description="e.g. INE_RESPONSABLE, CARTA_RESPONSIVA"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Upload a document for an evidence requirement (customer portal). Allowed: PDF, JPG, PNG; max 10 MB."""
    tenant_id = request.state.tenant_id
    order = _get_order_by_reservation_for_customer(request, reservation_id, tenant_id, db)
    order_id = order.id
    content_type = (file.content_type or "").strip().lower()
    suffix = Path(file.filename or "").suffix.lower()
    if content_type not in ALLOWED_EVIDENCE_CONTENT_TYPES and suffix not in ALLOWED_EVIDENCE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Allowed types: PDF, JPG, PNG",
        )
    content = file.file.read()
    if len(content) > MAX_EVIDENCE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large; max 10 MB",
        )
    evidence = (
        db.query(EvidenceRequirement)
        .filter(
            EvidenceRequirement.master_service_order_id == order_id,
            EvidenceRequirement.tenant_id == tenant_id,
            EvidenceRequirement.tipo_documento == tipo_documento,
        )
        .first()
    )
    if not evidence:
        evidence = EvidenceRequirement(
            tenant_id=tenant_id,
            master_service_order_id=order_id,
            tipo_documento=tipo_documento,
            estado=EvidenceStatus.PENDIENTE,
            plazo_vence_at=datetime.now(timezone.utc),
        )
        db.add(evidence)
        db.flush()
    ext = suffix if suffix in ALLOWED_EVIDENCE_EXTENSIONS else ".pdf"
    storage = Path(settings.EVIDENCE_STORAGE_PATH)
    storage.mkdir(parents=True, exist_ok=True)
    safe_name = f"{evidence.id}{ext}"
    full_path = storage / safe_name
    full_path.write_bytes(content)
    evidence.file_path = safe_name
    evidence.filename = file.filename or safe_name
    evidence.file_size_bytes = len(content)
    evidence.estado = EvidenceStatus.PENDIENTE_REVISION
    evidence.uploaded_at = datetime.now(timezone.utc)
    evidence.intentos_carga = (evidence.intentos_carga or 0) + 1
    db.commit()
    db.refresh(evidence)
    return evidence


@router.delete(
    "/reservations/{reservation_id}/evidence/{evidence_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_evidence_by_reservation(
    request: Request,
    reservation_id: UUID,
    evidence_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Remove uploaded document for an evidence requirement. Customer only, own reservation. Allowed only when estado is PENDIENTE, PENDIENTE_REVISION or RECHAZADO (not APROBADO)."""
    order = _get_order_by_reservation_for_customer(request, reservation_id, request.state.tenant_id, db)
    ev = (
        db.query(EvidenceRequirement)
        .filter(
            EvidenceRequirement.id == evidence_id,
            EvidenceRequirement.master_service_order_id == order.id,
            EvidenceRequirement.tenant_id == request.state.tenant_id,
        )
        .first()
    )
    if not ev:
        return  # idempotent: already deleted or wrong id
    if ev.estado == EvidenceStatus.APROBADO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede eliminar un documento ya aprobado.",
        )
    if ev.file_path:
        full_path = Path(settings.EVIDENCE_STORAGE_PATH) / ev.file_path
        if full_path.exists():
            try:
                full_path.unlink()
            except OSError:
                pass
    ev.file_path = None
    ev.filename = None
    ev.file_size_bytes = None
    ev.sha256_hash = None
    ev.uploaded_at = None
    ev.estado = EvidenceStatus.PENDIENTE
    ev.revisado_at = None
    ev.motivo_rechazo = None
    db.commit()
    return


@router.get(
    "/reservations/{reservation_id}/evidence/{evidence_id}/download",
    response_class=FileResponse,
)
def download_evidence_by_reservation(
    request: Request,
    reservation_id: UUID,
    evidence_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Download an evidence file (customer portal). Customer must own the reservation."""
    order = _get_order_by_reservation_for_customer(request, reservation_id, request.state.tenant_id, db)
    ev = _get_evidence_or_404(evidence_id, request.state.tenant_id, db)
    if ev.master_service_order_id != order.id or not ev.file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    full_path = Path(settings.EVIDENCE_STORAGE_PATH) / ev.file_path
    if not full_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return FileResponse(
        str(full_path),
        filename=ev.filename or "document",
        media_type="application/octet-stream",
    )


@router.get(
    "/service-orders/{order_id}/evidence/{evidence_id}/download",
    response_class=FileResponse,
)
def download_evidence(
    request: Request,
    order_id: UUID,
    evidence_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Download the file for an evidence requirement."""
    tenant_id = request.state.tenant_id
    _get_order_or_404(order_id, tenant_id, db)
    ev = _get_evidence_or_404(evidence_id, tenant_id, db)
    if ev.master_service_order_id != order_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found for this order")
    if not ev.file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    full_path = Path(settings.EVIDENCE_STORAGE_PATH) / ev.file_path
    if not full_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return FileResponse(
        str(full_path),
        filename=ev.filename or "document",
        media_type="application/octet-stream",
    )


@router.patch("/service-order-evidence/{evidence_id}", response_model=EvidenceRequirementRead)
def review_evidence(
    request: Request,
    evidence_id: UUID,
    body: EvidenceRequirementReview,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
    __: None = Depends(require_operations_or_admin),
):
    """Approve or reject an evidence document. Requires OPERATIONS or SUPERADMIN."""
    if body.estado not in (EvidenceStatus.APROBADO, EvidenceStatus.RECHAZADO):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="estado must be APROBADO or RECHAZADO",
        )
    if body.estado == EvidenceStatus.RECHAZADO and not body.motivo_rechazo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="motivo_rechazo required when rejecting",
        )
    tenant_id = request.state.tenant_id
    ev = _get_evidence_or_404(evidence_id, tenant_id, db)
    ev.estado = body.estado
    ev.revisado_at = datetime.now(timezone.utc)
    ev.motivo_rechazo = body.motivo_rechazo if body.estado == EvidenceStatus.RECHAZADO else None
    db.commit()
    db.refresh(ev)
    # Re-evaluate readiness when approving; may transition OS to READY
    if body.estado == EvidenceStatus.APROBADO:
        compute_readiness(ev.master_service_order_id, db)
        db.commit()
    return ev
