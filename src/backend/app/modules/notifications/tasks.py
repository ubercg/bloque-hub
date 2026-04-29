"""Tareas Celery para envío asíncrono de notificaciones por email."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select

from app.core.config import settings
from app.db.session import get_db_context
from app.modules.booking.models import Reservation, ReservationStatus
from app.modules.identity.models import User
from app.modules.inventory.models import Space
from app.modules.notifications.email_service import send_email
from app.modules.notifications.models import NotificationLog
from app.modules.notifications.templating import render
from app.modules.notifications.pase_caja import (
    build_pase_de_caja_context,
    build_pase_de_caja_event_context,
    render_pase_de_caja_email_html,
)

from app.celery_app import app


def _load_reservation(reservation_id: UUID):
    with get_db_context(tenant_id=None, role="SUPERADMIN") as db:
        r = db.get(Reservation, reservation_id)
        if r is None:
            return None, None, None, None
        user = db.get(User, r.user_id)
        space = db.get(Space, r.space_id)
        return r, user, space, None


def _fmt_time(t) -> str:
    if t is None:
        return ""
    return t.strftime("%H:%M") if hasattr(t, "strftime") else str(t)


def _fmt_date(d) -> str:
    if d is None:
        return ""
    return d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)


def _fmt_datetime(dt) -> str:
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M") if hasattr(dt, "strftime") else str(dt)


def _base_context(reservation, user, space):
    portal = settings.PORTAL_BASE_URL.rstrip("/")
    link_portal = f"{portal}/reservations/{reservation.id}" if reservation else portal
    link_upload_slip = f"{portal}/reservations/{reservation.id}/upload-slip" if reservation else None
    customer_name = (user.full_name if user else "") or "Cliente"
    space_name = (space.name if space else "") or "Espacio"
    fecha = _fmt_date(reservation.fecha) if reservation else ""
    hora_inicio = _fmt_time(reservation.hora_inicio) if reservation else ""
    hora_fin = _fmt_time(reservation.hora_fin) if reservation else ""
    folio = str(reservation.id) if reservation else ""
    return {
        "customer_name": customer_name,
        "space_name": space_name,
        "fecha": fecha,
        "hora_inicio": hora_inicio,
        "hora_fin": hora_fin,
        "folio": folio,
        "link_portal": link_portal,
        "link_upload_slip": link_upload_slip,
    }


@app.task(name="notifications.send_pre_reserva_emails")
def send_pre_reserva_emails(reservation_id: str) -> None:
    rid = UUID(reservation_id)
    reservation, user, space, _ = _load_reservation(rid)
    if reservation is None:
        return
    ctx = _base_context(reservation, user, space)
    ctx["monto"] = f"${space.precio_por_hora:,.2f}" if space else "Consultar"
    html = render("pre_reserva_iniciada.html", **ctx)
    to = user.email if user else None
    if to:
        send_email(to, "Pre-reserva iniciada — BLOQUE", html)
    commercial_email = getattr(settings, "NOTIFICATION_COMMERCIAL_EMAIL", None) or settings.SMTP_FROM
    ctx["customer_email"] = to or ""
    html_comercial = render("pre_reserva_comercial.html", **ctx)
    send_email(commercial_email, "Nueva pre-reserva — BLOQUE", html_comercial)


@app.task(name="notifications.send_pase_de_caja_email")
def send_pase_de_caja_email(
    reservation_id: str,
    included_reservation_ids: list[str] | None = None,
) -> None:
    rid = UUID(reservation_id)
    with get_db_context(tenant_id=None, role="SUPERADMIN") as db:
        if included_reservation_ids is not None:
            ids = [UUID(x) for x in included_reservation_ids]
            ctx = build_pase_de_caja_event_context(db, rid, ids)
        else:
            ctx = build_pase_de_caja_context(db, rid)
        if ctx is None:
            return
        reservation = db.get(Reservation, rid)
        user = db.get(User, reservation.user_id) if reservation else None
        html = render_pase_de_caja_email_html(ctx)
    to = user.email if user else None
    if to:
        send_email(to, "Pase de Caja — BLOQUE", html)


@app.task(name="notifications.send_recordatorio_ttl_email")
def send_recordatorio_ttl_email(reservation_id: str) -> None:
    rid = UUID(reservation_id)
    reservation, user, space, _ = _load_reservation(rid)
    if reservation is None:
        return
    ctx = _base_context(reservation, user, space)
    ctx["ttl_expires_at"] = _fmt_datetime(reservation.ttl_expires_at)
    html = render("recordatorio_ttl.html", **ctx)
    to = user.email if user else None
    if to:
        send_email(to, "Tu reserva expira pronto — BLOQUE", html)


@app.task(name="notifications.send_confirmacion_con_qr_email")
def send_confirmacion_con_qr_email(reservation_id: str) -> None:
    rid = UUID(reservation_id)
    reservation, user, space, _ = _load_reservation(rid)
    if reservation is None:
        return
    ctx = _base_context(reservation, user, space)
    ctx["link_download_qr"] = f"{settings.PORTAL_BASE_URL.rstrip('/')}/reservations/{reservation.id}/qr"
    html = render("confirmacion_con_qr.html", **ctx)
    to = user.email if user else None
    if to:
        send_email(to, "Tu reserva está confirmada — BLOQUE", html)


@app.task(name="notifications.send_portal_message_notification")
def send_portal_message_notification(message_id: str) -> None:
    """Envía email al destinatario: si remitente es CUSTOMER → staff; si STAFF → cliente."""
    from app.modules.notifications.models import PortalMessage, RemitenteTipo

    mid = UUID(message_id)
    with get_db_context(tenant_id=None, role="SUPERADMIN") as db:
        msg = db.get(PortalMessage, mid)
        if msg is None:
            return
        reservation = db.get(Reservation, msg.reservation_id)
        if reservation is None:
            return
        portal = settings.PORTAL_BASE_URL.rstrip("/")
        link_portal = f"{portal}/reservations/{reservation.id}/messages"
        if msg.remitente_tipo == RemitenteTipo.STAFF.value:
            recipient = db.get(User, reservation.user_id)
            to = recipient.email if recipient else None
            recipient_name = (recipient.full_name if recipient else "") or "Cliente"
        else:
            to = getattr(settings, "NOTIFICATION_COMMERCIAL_EMAIL", None) or settings.SMTP_FROM
            recipient_name = "Equipo comercial"
        ctx = {"recipient_name": recipient_name, "link_portal": link_portal}
        html = render("portal_nuevo_mensaje.html", **ctx)
        if to:
            send_email(to, "Nuevo mensaje en el Portal — BLOQUE", html)


@app.task(name="notifications.send_ttl_reminders")
def send_ttl_reminders() -> int:
    """
    Busca reservas con ttl_frozen=false, ttl_expires_at en ~4h, estado PENDING_SLIP o AWAITING_PAYMENT,
    y que no tengan ya un recordatorio enviado; encola send_recordatorio_ttl_email.
    """
    now = datetime.now(timezone.utc)
    window_start = now + timedelta(hours=3, minutes=30)
    window_end = now + timedelta(hours=4, minutes=30)
    count = 0
    with get_db_context(tenant_id=None, role="SUPERADMIN") as db:
        stmt = (
            select(Reservation.id)
            .where(Reservation.ttl_frozen.is_(False))
            .where(Reservation.ttl_expires_at.isnot(None))
            .where(Reservation.ttl_expires_at >= window_start)
            .where(Reservation.ttl_expires_at <= window_end)
            .where(
                Reservation.status.in_(
                    [ReservationStatus.PENDING_SLIP, ReservationStatus.AWAITING_PAYMENT]
                )
            )
        )
        candidate_ids = [row[0] for row in db.execute(stmt).all()]
        for rid in candidate_ids:
            exists = db.execute(
                select(NotificationLog.id).where(
                    NotificationLog.reservation_id == rid,
                    NotificationLog.notification_type == "recordatorio_ttl",
                )
            ).first()
            if exists:
                continue
            log = NotificationLog(reservation_id=rid, notification_type="recordatorio_ttl")
            db.add(log)
            db.commit()
            send_recordatorio_ttl_email.delay(str(rid))
            count += 1
    return count
