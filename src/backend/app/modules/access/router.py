"""REST API for access gate (QR validation) and QR download."""

import io
from datetime import datetime, timezone
from uuid import UUID

import qrcode
from fastapi import APIRouter, Depends, Request, status
from fastapi.exceptions import HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.dependencies.auth import require_operations_or_admin, require_tenant
from app.modules.access.models import AccessQRToken
from app.modules.access.schemas import ValidateQRBody, ValidateQRResponse
from app.modules.fulfillment.models import MasterServiceOrder
from app.modules.fulfillment.services import get_readiness

router = APIRouter(prefix="/api", tags=["access"])


@router.post("/access/validate-qr", response_model=ValidateQRResponse)
def validate_qr(
    request: Request,
    body: ValidateQRBody,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
    __: None = Depends(require_operations_or_admin),
):
    """
    Gate: validate QR token and readiness. Returns AUTORIZADO (verde) or RECHAZADO (rojo).
    Requires OPERATIONS or SUPERADMIN (scanner device / security staff).
    """
    token_str = (body.token or "").strip()
    if not token_str:
        return ValidateQRResponse(
            acceso="RECHAZADO",
            color="ROJO",
            motivo="QR inválido o fuera de horario",
        )

    qr = (
        db.query(AccessQRToken)
        .options(joinedload(AccessQRToken.reservation).joinedload("space"))
        .filter(AccessQRToken.token_qr == token_str)
        .first()
    )
    if not qr:
        return ValidateQRResponse(
            acceso="RECHAZADO",
            color="ROJO",
            motivo="QR inválido o fuera de horario",
        )

    now = datetime.now(timezone.utc)
    if now < qr.valid_from or now > qr.valid_until:
        return ValidateQRResponse(
            acceso="RECHAZADO",
            color="ROJO",
            motivo="QR inválido o fuera de horario",
        )

    order = (
        db.query(MasterServiceOrder)
        .filter(MasterServiceOrder.reservation_id == qr.reservation_id)
        .first()
    )
    if not order:
        return ValidateQRResponse(
            acceso="RECHAZADO",
            color="ROJO",
            motivo="Orden de servicio no encontrada. Contactar a Operaciones.",
        )

    result = get_readiness(order.id, db)
    if result is None:
        return ValidateQRResponse(
            acceso="RECHAZADO",
            color="ROJO",
            motivo="No se pudo verificar la preparación. Contactar a Operaciones.",
        )

    is_ready, checklist_pct, evidence_complete, details = result
    if not is_ready:
        return ValidateQRResponse(
            acceso="RECHAZADO",
            color="ROJO",
            motivo="Espacio no preparado (OS no READY). Contactar a Operaciones.",
            readiness_pct=checklist_pct,
            pending_critical_items=details.get("pending_critical_items"),
            pending_evidence=details.get("pending_evidence"),
        )

    # Authorized: record scan and return success
    qr.scanned_at = now
    if getattr(request.state, "user_id", None):
        qr.scanned_by = request.state.user_id
    db.commit()

    reservation = qr.reservation
    space_name = reservation.space.name if reservation.space else "—"
    nombre_evento = f"{space_name} — {reservation.fecha}"

    return ValidateQRResponse(
        acceso="AUTORIZADO",
        color="VERDE",
        motivo="Bienvenido a BLOQUE",
        nombre_evento=nombre_evento,
        espacio=space_name,
    )


@router.get("/access/reservations/{reservation_id}/qr", response_class=Response)
def get_qr_image(
    request: Request,
    reservation_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """
    Return QR code image (PNG) for the reservation. Same tenant only.
    Used by customer portal / email link to download QR for access.
    """
    from app.modules.booking.models import Reservation

    tenant_id = request.state.tenant_id
    qr = (
        db.query(AccessQRToken)
        .join(Reservation, AccessQRToken.reservation_id == Reservation.id)
        .filter(
            AccessQRToken.reservation_id == reservation_id,
            Reservation.tenant_id == tenant_id,
        )
        .first()
    )
    if not qr:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="QR no encontrado para esta reserva",
        )
    img = qrcode.make(qr.token_qr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="image/png",
        headers={"Content-Disposition": "inline; filename=qr-acceso.png"},
    )
