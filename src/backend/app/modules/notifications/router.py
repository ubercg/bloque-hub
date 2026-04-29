"""API de mensajería del Portal del Cliente (portal_messages)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.exceptions import HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import require_tenant
from app.modules.booking.models import Reservation
from app.modules.notifications.models import PortalMessage, RemitenteTipo
from app.modules.notifications.schemas import PortalMessageCreate, PortalMessageRead

router = APIRouter(prefix="/api", tags=["portal-messages"])

ALLOWED_STAFF_MESSAGES = {"COMMERCIAL", "OPERATIONS", "SUPERADMIN"}


def _can_access_reservation_messages(request: Request, reservation: Reservation) -> bool:
    """True si el usuario es el cliente de la reserva o staff del tenant."""
    user_id = getattr(request.state, "user_id", None)
    role = getattr(request.state, "role", None)
    if user_id is None:
        return False
    if reservation.user_id == user_id:
        return True
    return role in ALLOWED_STAFF_MESSAGES


@router.post("/reservations/{reservation_id}/messages", response_model=PortalMessageRead, status_code=status.HTTP_201_CREATED)
def create_message(
    request: Request,
    reservation_id: UUID,
    body: PortalMessageCreate,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Crea un mensaje en el hilo de la reserva. remitente_tipo implícito: CUSTOMER si es el cliente, STAFF si es staff."""
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found")
    tenant_id = request.state.tenant_id
    if str(reservation.tenant_id) != str(tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found")
    if not _can_access_reservation_messages(request, reservation):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot access this reservation's messages")
    user_id = request.state.user_id
    role = getattr(request.state, "role", None)
    remitente_tipo = RemitenteTipo.CUSTOMER.value if (user_id == reservation.user_id) else RemitenteTipo.STAFF.value
    msg = PortalMessage(
        tenant_id=tenant_id,
        reservation_id=reservation_id,
        remitente_tipo=remitente_tipo,
        remitente_id=user_id,
        mensaje=body.mensaje,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    from app.modules.notifications.tasks import send_portal_message_notification
    send_portal_message_notification.delay(str(msg.id))
    return msg


@router.get("/reservations/{reservation_id}/messages", response_model=list[PortalMessageRead])
def list_messages(
    request: Request,
    reservation_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Lista mensajes del hilo de la reserva, ordenados por enviado_at."""
    reservation = db.get(Reservation, reservation_id)
    if reservation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found")
    if str(reservation.tenant_id) != str(request.state.tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found")
    if not _can_access_reservation_messages(request, reservation):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot access this reservation's messages")
    messages = (
        db.query(PortalMessage)
        .filter(PortalMessage.reservation_id == reservation_id)
        .order_by(PortalMessage.enviado_at)
        .all()
    )
    return messages


@router.patch("/messages/{message_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_message_read(
    request: Request,
    message_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Marca un mensaje como leído (leido_at)."""
    msg = db.get(PortalMessage, message_id)
    if msg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    if str(msg.tenant_id) != str(request.state.tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    reservation = db.get(Reservation, msg.reservation_id)
    if reservation is None or not _can_access_reservation_messages(request, reservation):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot access this message")
    from datetime import datetime, timezone
    msg.leido_at = datetime.now(timezone.utc)
    db.commit()
    return None
