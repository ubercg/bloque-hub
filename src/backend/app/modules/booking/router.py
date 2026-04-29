"""REST API for reservations (SEMI_DIRECT flow)."""

import json
from datetime import date
from decimal import Decimal
from uuid import UUID
from typing import Optional

from pathlib import Path

from fastapi import APIRouter, Depends, Request, UploadFile, File, Form, Query, status
from fastapi.exceptions import HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.permissions import STAFF_ROLES
from app.db.session import get_db
from app.dependencies.auth import require_tenant, require_commercial_or_admin, require_finance_approval, require_finance_or_admin
from app.dependencies.events import get_event_dispatcher
from app.modules.booking.models import Reservation, ReservationStatus
from app.modules.booking.schemas import (
    BulkGenerateSlipBody,
    BulkSlipPreviewResponse,
    ReservationCreate,
    ReservationRead,
    RejectBody,
    PaymentVoucherRead,
    SlipPreviewItem,
)
from app.modules.booking.schemas import ReservationEventCreate, ReservationEventRead, EventSummaryResponse
from app.modules.booking.event_summary import build_event_summary_dict, list_reservations_for_event
from app.modules.booking.precotizacion_pdf import generate_event_precotizacion_pdf_bytes
from app.modules.identity.models import User
from app.modules.booking.services import (
    InvalidStateTransitionError,
    can_cancel_reservation,
    cancel_reservation,
    create_reservation,
    create_reservations_for_event,
    transition_to_awaiting_payment,
    transition_to_payment_under_review,
    confirm_payment,
    reject_payment,
    upload_payment_voucher,
    release_inventory_for_reservation,
)
from app.modules.booking.anti_hoarding import check_anti_hoarding
from app.modules.inventory.services import SlotNotAvailableError
from app.modules.access.services import create_qr_token_for_reservation
from app.modules.audit.service import append_audit_log
from app.modules.finance.models import CfdiDocument
from app.modules.finance.schemas import CfdiDocumentRead
from app.modules.fulfillment.schemas import ReadinessDetail, ReadinessRead
from app.modules.fulfillment.services import get_readiness_by_reservation_id
from app.modules.discounts.services import (
    DiscountValidationError,
    register_discount_usage,
    validate_code_for_subtotal,
)
from app.modules.pricing.services import NoPricingRuleError, get_quote_for_space
from app.modules.reservation_documents.services import build_completeness, upload_document_version

router = APIRouter(prefix="/api", tags=["booking"])


def _slot_duration_hours(hora_inicio, hora_fin) -> Decimal:
    start_minutes = hora_inicio.hour * 60 + hora_inicio.minute
    end_minutes = hora_fin.hour * 60 + hora_fin.minute
    diff = max(0, end_minutes - start_minutes)
    return (Decimal(diff) / Decimal(60)).quantize(Decimal("0.01"))


def _compute_event_subtotal(tenant_id: UUID, items, db: Session) -> Decimal:
    subtotal = Decimal("0.00")
    for item in items:
        duration = _slot_duration_hours(item.hora_inicio, item.hora_fin)
        quote = get_quote_for_space(
            db=db,
            tenant_id=tenant_id,
            space_id=item.space_id,
            target_date=item.fecha,
            duration_hours=duration,
        )
        subtotal += Decimal(quote["total_price"])
    return subtotal.quantize(Decimal("0.01"))


def _get_reservation_or_404(reservation_id: UUID, db: Session) -> Reservation:
    r = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    if r is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found")
    return r


def _ensure_customer_owns_reservation(request: Request, reservation: Reservation, role: str | None) -> None:
    """Raise 403 if CUSTOMER tries to access another user's reservation."""
    if role != "CUSTOMER":
        return
    user_id = getattr(request.state, "user_id", None)
    if user_id is None or reservation.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo puedes acceder a tus propias reservas.",
        )


@router.post("/reservations", response_model=ReservationRead, status_code=status.HTTP_201_CREATED)
def post_reservation(
    request: Request,
    body: ReservationCreate,
    db: Session = Depends(get_db),
    tenant_data: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Create a pre-reserva (PENDING_SLIP) and block the slot. Requires authenticated user (user_id in JWT). Anti-hoarding: max 3 active reservations per CUSTOMER."""
    tenant_id, role = tenant_data
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User identity required to create a reservation",
        )
    check_anti_hoarding(db, tenant_id, user_id, role)
    client_ip = request.client.host if request.client else None
    device_fingerprint = request.headers.get("X-Device-Fingerprint")
    try:
        reservation = create_reservation(
            tenant_id=tenant_id,
            user_id=user_id,
            space_id=body.space_id,
            fecha=body.fecha,
            hora_inicio=body.hora_inicio,
            hora_fin=body.hora_fin,
            db=db,
            created_from_ip=client_ip,
            device_fingerprint=device_fingerprint or None,
        )
        db.commit()
        db.refresh(reservation)
        from app.modules.notifications.tasks import send_pre_reserva_emails
        send_pre_reserva_emails.delay(str(reservation.id))
        return reservation
    except SlotNotAvailableError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SLOT_NO_DISPONIBLE",
        )


@router.post("/reservation-events", response_model=ReservationEventRead, status_code=status.HTTP_201_CREATED)
def post_event_reservation(
    request: Request,
    body: ReservationEventCreate,
    db: Session = Depends(get_db),
    tenant_data: tuple[UUID, str | None] = Depends(require_tenant),
):
    """
    Create one event reservation composed of 1..N space slots.
    All slots are created atomically and linked by group_event_id.
    """
    tenant_id, role = tenant_data
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User identity required to create a reservation",
        )

    # Anti-hoarding unificado:
    # máximo 3 reservas activas lógicas por usuario CUSTOMER.
    # Un evento con group_event_id cuenta como 1.
    check_anti_hoarding(db, tenant_id, user_id, role)

    client_ip = request.client.host if request.client else None
    device_fingerprint = request.headers.get("X-Device-Fingerprint")
    try:
        subtotal = _compute_event_subtotal(tenant_id, body.items, db)
        discount_code = None
        discount_amount = Decimal("0.00")
        discounted_total = subtotal
        if body.discount_code:
            try:
                discount_code, discount_amount, discounted_total = validate_code_for_subtotal(
                    db=db,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    code=body.discount_code,
                    subtotal=subtotal,
                )
            except DiscountValidationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=exc.reason,
                )

        group_event_id, reservations = create_reservations_for_event(
            tenant_id=tenant_id,
            user_id=user_id,
            items=[
                (it.space_id, it.fecha, it.hora_inicio, it.hora_fin)
                for it in body.items
            ],
            db=db,
            created_from_ip=client_ip,
            device_fingerprint=device_fingerprint or None,
            event_name=body.event_name,
        )
        if discount_code is not None and reservations:
            per_reservation = (discount_amount / Decimal(len(reservations))).quantize(Decimal("0.01"))
            assigned = Decimal("0.00")
            for idx, reservation in enumerate(reservations):
                amount = per_reservation if idx < len(reservations) - 1 else (discount_amount - assigned)
                reservation.discount_code_id = discount_code.id
                reservation.discount_amount_applied = amount
                assigned += amount

            register_discount_usage(
                db=db,
                tenant_id=tenant_id,
                discount_code=discount_code,
                user_id=user_id,
                subtotal=subtotal,
                discount_amount=discount_amount,
                total=discounted_total,
                group_event_id=group_event_id,
                reservation_id=reservations[0].id,
            )

        db.commit()
        for reservation in reservations:
            db.refresh(reservation)
            from app.modules.notifications.tasks import send_pre_reserva_emails
            send_pre_reserva_emails.delay(str(reservation.id))
        return ReservationEventRead(
            group_event_id=group_event_id,
            event_name=body.event_name,
            reservations=[ReservationRead.model_validate(r) for r in reservations],
        )
    except SlotNotAvailableError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SLOT_NO_DISPONIBLE",
        )


@router.post(
    "/reservation-events/with-documents",
    response_model=ReservationEventRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_event_reservation_with_documents(
    request: Request,
    payload: str = Form(..., description="JSON ReservationEventCreate"),
    document_type_ids: str = Form(
        ...,
        description="JSON array de UUIDs (mismo orden y cantidad que los archivos en files)",
    ),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    tenant_data: tuple[UUID, str | None] = Depends(require_tenant),
):
    """
    Crea el evento de reserva y sube los documentos KYC en una sola transacción.
    Si falla la subida o la completitud documental, se hace rollback (no queda solicitud huérfana).
    """
    body = ReservationEventCreate.model_validate_json(payload)
    try:
        raw_ids = json.loads(document_type_ids)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="document_type_ids debe ser JSON válido",
        ) from e
    if not isinstance(raw_ids, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="document_type_ids debe ser un array",
        )
    if len(raw_ids) != len(files):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="document_type_ids y files deben tener la misma longitud",
        )
    type_uuids = [UUID(str(x)) for x in raw_ids]

    tenant_id, role = tenant_data
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User identity required to create a reservation",
        )

    check_anti_hoarding(db, tenant_id, user_id, role)

    client_ip = request.client.host if request.client else None
    device_fingerprint = request.headers.get("X-Device-Fingerprint")
    try:
        subtotal = _compute_event_subtotal(tenant_id, body.items, db)
        discount_code = None
        discount_amount = Decimal("0.00")
        discounted_total = subtotal
        if body.discount_code:
            try:
                discount_code, discount_amount, discounted_total = validate_code_for_subtotal(
                    db=db,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    code=body.discount_code,
                    subtotal=subtotal,
                )
            except DiscountValidationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=exc.reason,
                )

        group_event_id, reservations = create_reservations_for_event(
            tenant_id=tenant_id,
            user_id=user_id,
            items=[
                (it.space_id, it.fecha, it.hora_inicio, it.hora_fin)
                for it in body.items
            ],
            db=db,
            created_from_ip=client_ip,
            device_fingerprint=device_fingerprint or None,
            event_name=body.event_name,
        )
        if discount_code is not None and reservations:
            per_reservation = (discount_amount / Decimal(len(reservations))).quantize(Decimal("0.01"))
            assigned = Decimal("0.00")
            for idx, reservation in enumerate(reservations):
                amount = per_reservation if idx < len(reservations) - 1 else (discount_amount - assigned)
                reservation.discount_code_id = discount_code.id
                reservation.discount_amount_applied = amount
                assigned += amount

            register_discount_usage(
                db=db,
                tenant_id=tenant_id,
                discount_code=discount_code,
                user_id=user_id,
                subtotal=subtotal,
                discount_amount=discount_amount,
                total=discounted_total,
                group_event_id=group_event_id,
                reservation_id=reservations[0].id,
            )

        for dt_id, up in zip(type_uuids, files, strict=True):
            content = await up.read()
            mime = up.content_type or "application/octet-stream"
            name = up.filename or "upload"
            try:
                upload_document_version(
                    db,
                    tenant_id=tenant_id,
                    group_event_id=group_event_id,
                    user_id=user_id,
                    document_type_id=dt_id,
                    file_content=content,
                    original_filename=name,
                    mime_type=mime,
                    actor_ip=client_ip,
                    user_agent=request.headers.get("User-Agent"),
                )
            except ValueError as e:
                db.rollback()
                code = str(e.args[0]) if e.args else "UPLOAD_ERROR"
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=code,
                ) from e

        comp = build_completeness(db, tenant_id=tenant_id, group_event_id=group_event_id)
        if not comp.is_complete:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="DOCUMENTATION_INCOMPLETE",
            )

        db.commit()
        for reservation in reservations:
            db.refresh(reservation)
            from app.modules.notifications.tasks import send_pre_reserva_emails

            send_pre_reserva_emails.delay(str(reservation.id))
        return ReservationEventRead(
            group_event_id=group_event_id,
            event_name=body.event_name,
            reservations=[ReservationRead.model_validate(r) for r in reservations],
        )
    except SlotNotAvailableError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SLOT_NO_DISPONIBLE",
        )


@router.get("/reservations", response_model=list[ReservationRead])
def list_reservations(
    request: Request,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
    status: Optional[ReservationStatus] = Query(None, description="Filter by reservation status"),
    date_from: Optional[date] = Query(None, description="Filter reservations from this date (inclusive)"),
    date_to: Optional[date] = Query(None, description="Filter reservations until this date (inclusive)"),
):
    """List reservations for the current tenant (RLS applies). For CUSTOMER role, only their own reservations."""
    q = db.query(Reservation)
    role = getattr(request.state, "role", None)
    user_id = getattr(request.state, "user_id", None)
    if role == "CUSTOMER" and user_id is not None:
        q = q.filter(Reservation.user_id == user_id)
    if status is not None:
        q = q.filter(Reservation.status == status)
    if date_from is not None:
        q = q.filter(Reservation.fecha >= date_from)
    if date_to is not None:
        q = q.filter(Reservation.fecha <= date_to)
    return q.all()


@router.post("/reservations/bulk/generate-slip", status_code=status.HTTP_204_NO_CONTENT)
def bulk_generate_slip(
    request: Request,
    body: BulkGenerateSlipBody,
    db: Session = Depends(get_db),
    tenant_data: tuple[UUID, str | None] = Depends(require_tenant),
    _: None = Depends(require_commercial_or_admin),
):
    """
    Transition all PENDING_SLIP reservations in a group to AWAITING_PAYMENT in one transaction.
    Pass either group_event_id (all slots of the event) or an explicit list of reservation_ids (same tenant).
    """
    tenant_id, _role = tenant_data
    if body.group_event_id is not None and body.reservation_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Send only group_event_id or reservation_ids, not both",
        )
    if body.group_event_id is None and not body.reservation_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="group_event_id or reservation_ids is required",
        )

    if body.group_event_id is not None:
        rows = (
            db.query(Reservation)
            .filter(
                Reservation.tenant_id == tenant_id,
                Reservation.group_event_id == body.group_event_id,
            )
            .all()
        )
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No reservations for this group_event_id",
            )
    else:
        assert body.reservation_ids is not None
        rows = (
            db.query(Reservation)
            .filter(
                Reservation.tenant_id == tenant_id,
                Reservation.id.in_(body.reservation_ids),
            )
            .all()
        )
        if len(rows) != len(set(body.reservation_ids)):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more reservations not found")

    pending = [r for r in rows if r.status == ReservationStatus.PENDING_SLIP]
    if not pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No reservations in PENDING_SLIP for this selection",
        )

    try:
        for reservation in pending:
            transition_to_awaiting_payment(reservation, db)
            append_audit_log(
                db,
                tenant_id=reservation.tenant_id,
                tabla="reservations",
                registro_id=reservation.id,
                accion="STATE_CHANGE",
                campo_modificado="status",
                valor_anterior={"status": "PENDING_SLIP"},
                valor_nuevo={"status": "AWAITING_PAYMENT"},
                actor_id=getattr(request.state, "user_id", None),
                actor_ip=request.client.host if request.client else None,
                actor_user_agent=request.headers.get("User-Agent"),
            )
        db.commit()
    except InvalidStateTransitionError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    from app.modules.notifications.tasks import send_pase_de_caja_email

    pending_sorted = sorted(pending, key=lambda r: (r.fecha, r.hora_inicio, r.id))
    anchor = pending_sorted[0]
    send_pase_de_caja_email.delay(str(anchor.id), [str(r.id) for r in pending])


@router.post("/reservations/bulk/generate-slip-preview", response_model=BulkSlipPreviewResponse)
def bulk_generate_slip_preview(
    body: BulkGenerateSlipBody,
    db: Session = Depends(get_db),
    tenant_data: tuple[UUID, str | None] = Depends(require_tenant),
    _: None = Depends(require_commercial_or_admin),
):
    """Vista previa HTML del Pase de Caja para todo el evento (slots PENDING_SLIP en la selección)."""
    from app.modules.notifications.pase_caja import build_pase_de_caja_event_context, render_pase_de_caja_email_html

    tenant_id, _role = tenant_data
    if body.group_event_id is not None and body.reservation_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Send only group_event_id or reservation_ids, not both",
        )
    if body.group_event_id is None and not body.reservation_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="group_event_id or reservation_ids is required",
        )

    if body.group_event_id is not None:
        rows = (
            db.query(Reservation)
            .filter(
                Reservation.tenant_id == tenant_id,
                Reservation.group_event_id == body.group_event_id,
            )
            .all()
        )
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No reservations for this group_event_id",
            )
    else:
        assert body.reservation_ids is not None
        rows = (
            db.query(Reservation)
            .filter(
                Reservation.tenant_id == tenant_id,
                Reservation.id.in_(body.reservation_ids),
            )
            .all()
        )
        if len(rows) != len(set(body.reservation_ids)):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more reservations not found")

    pending = [r for r in rows if r.status == ReservationStatus.PENDING_SLIP]
    if not pending:
        return BulkSlipPreviewResponse(items=[])
    pending_sorted = sorted(pending, key=lambda r: (r.fecha, r.hora_inicio, r.id))
    anchor = pending_sorted[0]
    ctx = build_pase_de_caja_event_context(db, anchor.id, [r.id for r in pending])
    if ctx is None:
        return BulkSlipPreviewResponse(items=[])
    html = render_pase_de_caja_email_html(ctx)
    return BulkSlipPreviewResponse(items=[SlipPreviewItem(reservation_id=anchor.id, html=html)])


@router.get("/reservations/{reservation_id}/event-summary", response_model=EventSummaryResponse)
def get_reservation_event_summary(
    request: Request,
    reservation_id: UUID,
    db: Session = Depends(get_db),
    tenant_data: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Resumen del evento agrupado por espacio y día, con bloques de tiempo fusionados."""
    reservation = _get_reservation_or_404(reservation_id, db)
    tenant_id, role = tenant_data
    _ensure_customer_owns_reservation(request, reservation, role)
    rows = list_reservations_for_event(db, tenant_id, reservation)
    payload = build_event_summary_dict(db, tenant_id, rows)
    return EventSummaryResponse.model_validate(payload)


@router.get("/reservations/{reservation_id}/event-precotizacion.pdf")
def get_reservation_event_precotizacion_pdf(
    request: Request,
    reservation_id: UUID,
    db: Session = Depends(get_db),
    tenant_data: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Precotización en PDF para el cliente (mismos datos que el resumen de precios por bloque)."""
    reservation = _get_reservation_or_404(reservation_id, db)
    tenant_id, role = tenant_data
    _ensure_customer_owns_reservation(request, reservation, role)
    rows = list_reservations_for_event(db, tenant_id, reservation)
    user = db.query(User).filter(User.id == reservation.user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    try:
        pdf_bytes = generate_event_precotizacion_pdf_bytes(
            db,
            tenant_id,
            rows,
            client_name=user.full_name,
            client_email=user.email,
        )
    except NoPricingRuleError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    gid = reservation.group_event_id or reservation.id
    filename = f"precotizacion-{gid}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reservations/{reservation_id}", response_model=ReservationRead)
def get_reservation(
    reservation_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Get one reservation by id."""
    return _get_reservation_or_404(reservation_id, db)


@router.get("/reservations/{reservation_id}/readiness", response_model=ReadinessRead)
def get_reservation_readiness(
    reservation_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Get readiness state for the service order linked to this reservation (portal del cliente)."""
    _get_reservation_or_404(reservation_id, db)
    result = get_readiness_by_reservation_id(reservation_id, db)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No service order found for this reservation yet",
        )
    is_ready, checklist_pct, evidence_complete, details = result
    return ReadinessRead(
        is_ready=is_ready,
        checklist_pct=checklist_pct,
        evidence_complete=evidence_complete,
        details=ReadinessDetail(
            pending_critical_items=details.get("pending_critical_items", []),
            pending_evidence=details.get("pending_evidence", []),
        ),
    )


@router.get("/reservations/{reservation_id}/cfdi", response_model=list[CfdiDocumentRead])
def get_reservation_cfdi_for_customer(
    request: Request,
    reservation_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """List CFDI documents for this reservation (portal del cliente). Only the reservation owner can access."""
    reservation = _get_reservation_or_404(reservation_id, db)
    user_id = getattr(request.state, "user_id", None)
    if user_id is None or reservation.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this reservation's CFDI",
        )
    rows = db.query(CfdiDocument).filter(CfdiDocument.reservation_id == reservation_id).all()
    return [CfdiDocumentRead.model_validate(r) for r in rows]


@router.post("/reservations/{reservation_id}/generate_slip", status_code=status.HTTP_204_NO_CONTENT)
def generate_slip(
    request: Request,
    reservation_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
    __: None = Depends(require_commercial_or_admin),
):
    """Generate Pase de Caja: transition to AWAITING_PAYMENT. Requires COMMERCIAL/FINANCE/SUPERADMIN."""
    reservation = _get_reservation_or_404(reservation_id, db)
    try:
        transition_to_awaiting_payment(reservation, db)
        append_audit_log(
            db,
            tenant_id=reservation.tenant_id,
            tabla="reservations",
            registro_id=reservation.id,
            accion="STATE_CHANGE",
            campo_modificado="status",
            valor_anterior={"status": "PENDING_SLIP"},
            valor_nuevo={"status": "AWAITING_PAYMENT"},
            actor_id=getattr(request.state, "user_id", None),
            actor_ip=request.client.host if request.client else None,
            actor_user_agent=request.headers.get("User-Agent"),
        )
        db.commit()
        from app.modules.notifications.tasks import send_pase_de_caja_email
        send_pase_de_caja_email.delay(str(reservation.id))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/reservations/{reservation_id}/upload_slip", response_model=PaymentVoucherRead, status_code=status.HTTP_201_CREATED)
def upload_slip(
    request: Request,
    reservation_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    tenant_data: tuple[UUID, str | None] = Depends(require_tenant),
):
    """
    Upload payment voucher (comprobante de pago SPEI) for a reservation.

    Validates file type (PDF/JPG/PNG/HEIC), size (5KB-10MB), and reservation status (must be AWAITING_PAYMENT or PAYMENT_UNDER_REVIEW).
    When status is AWAITING_PAYMENT, transitions to PAYMENT_UNDER_REVIEW and freezes TTL.
    When already PAYMENT_UNDER_REVIEW, allows adding another voucher (e.g. customer re-upload).

    Returns 201 Created with voucher data on success.
    """
    tenant_id, role = tenant_data
    reservation = _get_reservation_or_404(reservation_id, db)
    _ensure_customer_owns_reservation(request, reservation, role)

    from app.modules.booking.models import ReservationStatus
    if reservation.status not in (ReservationStatus.AWAITING_PAYMENT, ReservationStatus.PAYMENT_UNDER_REVIEW):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se puede subir comprobante: estado actual {reservation.status.value}. Solo en espera de pago o en revisión.",
        )

    # Validate file type
    ALLOWED_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/heic"}
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type: {file.content_type}. Allowed: PDF, JPG, PNG, HEIC",
        )

    # Read file content
    file_content = file.file.read()

    # Validate file size (5KB min, 10MB max)
    MIN_SIZE_KB = 5
    MAX_SIZE_KB = 10 * 1024  # 10 MB
    file_size_kb = len(file_content) // 1024

    if file_size_kb < MIN_SIZE_KB:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too small: {file_size_kb} KB (minimum {MIN_SIZE_KB} KB)",
        )

    if file_size_kb > MAX_SIZE_KB:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large: {file_size_kb} KB (maximum {MAX_SIZE_KB} KB)",
        )

    # Capture client IP
    client_ip = request.client.host if request.client else None

    try:
        # Transition to PAYMENT_UNDER_REVIEW only when still AWAITING_PAYMENT (freezes TTL)
        if reservation.status == ReservationStatus.AWAITING_PAYMENT:
            transition_to_payment_under_review(reservation, db)
            append_audit_log(
                db,
                tenant_id=reservation.tenant_id,
                tabla="reservations",
                registro_id=reservation.id,
                accion="STATE_CHANGE",
                campo_modificado="status",
                valor_anterior={"status": "AWAITING_PAYMENT"},
                valor_nuevo={"status": "PAYMENT_UNDER_REVIEW"},
                actor_id=getattr(request.state, "user_id", None),
                actor_ip=client_ip,
                actor_user_agent=request.headers.get("User-Agent"),
            )

        # Upload and save voucher (atomic: file + DB + expediente)
        voucher = upload_payment_voucher(
            reservation=reservation,
            file_content=file_content,
            file_type=file.content_type,
            tenant_id=tenant_id,
            uploaded_by_ip=client_ip,
            db=db,
        )
        db.commit()
        db.refresh(voucher)
        return voucher

    except InvalidStateTransitionError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except IntegrityError as e:
        db.rollback()
        # Check if it's a duplicate SHA-256 hash
        if "uq_payment_vouchers_sha256_hash" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Duplicate file detected: this voucher has already been uploaded",
            )
        # Re-raise other integrity errors
        raise
    except Exception:
        db.rollback()
        raise


@router.get("/reservations/{reservation_id}/vouchers", response_model=list[PaymentVoucherRead])
def list_vouchers(
    request: Request,
    reservation_id: UUID,
    db: Session = Depends(get_db),
    tenant_data: tuple[UUID, str | None] = Depends(require_tenant),
):
    """List all payment vouchers uploaded for this reservation. CUSTOMER only for own reservations."""
    reservation = _get_reservation_or_404(reservation_id, db)
    _ensure_customer_owns_reservation(request, reservation, tenant_data[1])
    from app.modules.booking.models import PaymentVoucher

    vouchers = (
        db.query(PaymentVoucher)
        .filter(PaymentVoucher.reservation_id == reservation.id)
        .order_by(PaymentVoucher.uploaded_at.desc())
        .all()
    )
    return vouchers


@router.get("/reservations/{reservation_id}/vouchers/{voucher_id}/download")
def download_voucher(
    request: Request,
    reservation_id: UUID,
    voucher_id: UUID,
    db: Session = Depends(get_db),
    tenant_data: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Download a payment voucher file. CUSTOMER only for own reservations."""
    reservation = _get_reservation_or_404(reservation_id, db)
    _ensure_customer_owns_reservation(request, reservation, tenant_data[1])
    from app.modules.booking.models import PaymentVoucher

    voucher = db.query(PaymentVoucher).filter(
        PaymentVoucher.id == voucher_id,
        PaymentVoucher.reservation_id == reservation_id,
    ).first()
    if not voucher:
        raise HTTPException(status_code=404, detail="Voucher not found")

    from app.core.config import settings
    file_path = Path(settings.PAYMENT_VOUCHERS_STORAGE_PATH) / voucher.file_url
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Voucher file not found on disk")

    return FileResponse(
        path=str(file_path),
        media_type=voucher.file_type,
        filename=voucher.file_url,
    )


@router.delete("/reservations/{reservation_id}/vouchers/{voucher_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_voucher(
    request: Request,
    reservation_id: UUID,
    voucher_id: UUID,
    db: Session = Depends(get_db),
    tenant_data: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Delete a payment voucher. Allowed only when reservation is AWAITING_PAYMENT or PAYMENT_UNDER_REVIEW. CUSTOMER only for own reservations."""
    from app.modules.booking.models import PaymentVoucher, ReservationStatus
    from app.core.config import settings

    reservation = _get_reservation_or_404(reservation_id, db)
    _ensure_customer_owns_reservation(request, reservation, tenant_data[1])

    if reservation.status not in (ReservationStatus.AWAITING_PAYMENT, ReservationStatus.PAYMENT_UNDER_REVIEW):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede eliminar el comprobante: la reserva ya fue confirmada o rechazada.",
        )

    voucher = db.query(PaymentVoucher).filter(
        PaymentVoucher.id == voucher_id,
        PaymentVoucher.reservation_id == reservation_id,
    ).first()
    if not voucher:
        # Idempotent: already deleted or never existed → 204 so client can refresh list
        return

    file_path = Path(settings.PAYMENT_VOUCHERS_STORAGE_PATH) / voucher.file_url
    if file_path.exists():
        try:
            file_path.unlink()
        except OSError:
            pass  # continue to delete DB record
    db.delete(voucher)
    db.commit()


@router.post("/reservations/{reservation_id}/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_reservation(
    request: Request,
    reservation_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
    __: None = Depends(require_finance_approval),
    event_dispatcher=Depends(get_event_dispatcher),
):
    """Approve payment: transition to CONFIRMED and set slot to RESERVED. Requires FINANCE or SUPERADMIN (SoD)."""
    reservation = _get_reservation_or_404(reservation_id, db)
    try:
        confirm_payment(reservation, db, event_dispatcher=event_dispatcher)
        create_qr_token_for_reservation(reservation, db)
        append_audit_log(
            db,
            tenant_id=reservation.tenant_id,
            tabla="reservations",
            registro_id=reservation.id,
            accion="STATE_CHANGE",
            campo_modificado="status",
            valor_anterior={"status": "PAYMENT_UNDER_REVIEW"},
            valor_nuevo={"status": "CONFIRMED"},
            actor_id=getattr(request.state, "user_id", None),
            actor_ip=request.client.host if request.client else None,
            actor_user_agent=request.headers.get("User-Agent"),
        )
        db.commit()
        from app.modules.notifications.tasks import send_confirmacion_con_qr_email
        send_confirmacion_con_qr_email.delay(str(reservation.id))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/reservations/{reservation_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel_reservation_request(
    request: Request,
    reservation_id: UUID,
    db: Session = Depends(get_db),
    tenant_data: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Cancel a reservation (solicitud). Allowed for PENDING_SLIP or AWAITING_PAYMENT. Owner (CUSTOMER) or COMMERCIAL/SUPERADMIN."""
    reservation = _get_reservation_or_404(reservation_id, db)
    user_id = getattr(request.state, "user_id", None)
    role = tenant_data[1] or ""
    if role == "CUSTOMER":
        if user_id is None or reservation.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo puedes cancelar tus propias solicitudes.",
            )
    elif role not in STAFF_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para cancelar esta reserva.",
        )

    # Si la reservación pertenece a un evento, cancelar todas las hermanas del mismo grupo.
    if reservation.group_event_id is not None:
        grouped_reservations = (
            db.query(Reservation)
            .filter(
                Reservation.tenant_id == reservation.tenant_id,
                Reservation.group_event_id == reservation.group_event_id,
            )
            .all()
        )
        if role == "CUSTOMER":
            grouped_reservations = [r for r in grouped_reservations if r.user_id == user_id]

        invalid = [
            r for r in grouped_reservations
            if not can_cancel_reservation(r.status)
            and r.status not in (ReservationStatus.CANCELLED, ReservationStatus.EXPIRED)
        ]
        if invalid:
            states = ", ".join(sorted({r.status.value for r in invalid}))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "No se puede cancelar el evento completo porque contiene reservas en estado "
                    f"{states}. Solo pre-reservas o esperando pago."
                ),
            )

        try:
            for r in grouped_reservations:
                if can_cancel_reservation(r.status):
                    old_status = r.status.value
                    cancel_reservation(r, db)
                    append_audit_log(
                        db,
                        tenant_id=r.tenant_id,
                        tabla="reservations",
                        registro_id=r.id,
                        accion="STATE_CHANGE",
                        campo_modificado="status",
                        valor_anterior={"status": old_status},
                        valor_nuevo={"status": "CANCELLED"},
                        actor_id=user_id,
                        actor_ip=request.client.host if request.client else None,
                        actor_user_agent=request.headers.get("User-Agent"),
                    )
                # Idempotente: si ya estaba cancelada/expirada, igual limpiamos inventario huérfano.
                release_inventory_for_reservation(r, db)
            db.commit()
            return
        except InvalidStateTransitionError as e:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not can_cancel_reservation(reservation.status):
        if reservation.status in (ReservationStatus.CANCELLED, ReservationStatus.EXPIRED):
            release_inventory_for_reservation(reservation, db)
            db.commit()
            return
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se puede cancelar una reserva en estado {reservation.status.value}. Solo pre-reservas o esperando pago.",
        )
    try:
        old_status = reservation.status.value
        cancel_reservation(reservation, db)
        append_audit_log(
            db,
            tenant_id=reservation.tenant_id,
            tabla="reservations",
            registro_id=reservation.id,
            accion="STATE_CHANGE",
            campo_modificado="status",
            valor_anterior={"status": old_status},
            valor_nuevo={"status": "CANCELLED"},
            actor_id=user_id,
            actor_ip=request.client.host if request.client else None,
            actor_user_agent=request.headers.get("User-Agent"),
        )
        db.commit()
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/reservations/{reservation_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
def reject_reservation(
    request: Request,
    reservation_id: UUID,
    body: RejectBody | None = None,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
    __: None = Depends(require_finance_approval),
):
    """Reject payment: transition to EXPIRED and release slot. Requires FINANCE or SUPERADMIN (SoD)."""
    reservation = _get_reservation_or_404(reservation_id, db)
    try:
        reject_payment(reservation, db)
        append_audit_log(
            db,
            tenant_id=reservation.tenant_id,
            tabla="reservations",
            registro_id=reservation.id,
            accion="STATE_CHANGE",
            campo_modificado="status",
            valor_anterior={"status": "PAYMENT_UNDER_REVIEW"},
            valor_nuevo={"status": "EXPIRED"},
            actor_id=getattr(request.state, "user_id", None),
            actor_ip=request.client.host if request.client else None,
            actor_user_agent=request.headers.get("User-Agent"),
        )
        db.commit()
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/reservations/{reservation_id}/audit-package")
def get_audit_package(
    request: Request,
    reservation_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
    __: None = Depends(require_finance_or_admin),
):
    """Exporta paquete ZIP Audit-Ready (manifest + certificado de integridad). Rol FINANCE o SUPERADMIN."""
    reservation = _get_reservation_or_404(reservation_id, db)
    from app.modules.expediente.audit_export import build_audit_package

    zip_bytes = build_audit_package(
        db,
        reservation_id=reservation_id,
        tenant_id=reservation.tenant_id,
    )
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=audit-package-{reservation_id}.zip",
        },
    )
