"""Celery tasks for booking (e.g. TTL expiration)."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.db.session import get_db_context
from app.modules.audit.service import append_audit_log
from app.modules.booking.models import Reservation, ReservationStatus
from app.modules.booking.services import expire_reservation_by_ttl
from app.modules.reservation_documents.models import ReservationDocument
from app.modules.reservation_documents.services import purge_kyc_drafts_for_group_if_all_terminal

# Import app so this module can be loaded after celery_app is created
from app.celery_app import app


@app.task(name="booking.expire_reservations_ttl")
def expire_reservations_ttl() -> int:
    """
    Find reservations with TTL expired (ttl_frozen=false, ttl_expires_at < now,
    status PENDING_SLIP or AWAITING_PAYMENT) and expire them, releasing inventory.
    Uses SUPERADMIN role so RLS allows reading/updating all tenants' reservations.
    Returns the number of reservations expired.
    """
    now = datetime.now(timezone.utc)
    with get_db_context(tenant_id=None, role="SUPERADMIN") as db:
        stmt = (
            select(Reservation.id)
            .where(Reservation.ttl_frozen.is_(False))
            .where(Reservation.ttl_expires_at.isnot(None))
            .where(Reservation.ttl_expires_at < now)
            .where(
                Reservation.status.in_(
                    [ReservationStatus.PENDING_SLIP, ReservationStatus.AWAITING_PAYMENT]
                )
            )
        )
        reservation_ids: list[UUID] = list(db.execute(stmt).scalars().all())
    count = 0
    for rid in reservation_ids:
        with get_db_context(tenant_id=None, role="SUPERADMIN") as db:
            reservation = db.get(Reservation, rid)
            if reservation is None:
                continue
            try:
                old_status = reservation.status.value
                expire_reservation_by_ttl(reservation, db)
                append_audit_log(
                    db,
                    tenant_id=reservation.tenant_id,
                    tabla="reservations",
                    registro_id=reservation.id,
                    accion="STATE_CHANGE",
                    campo_modificado="status",
                    valor_anterior={"status": old_status},
                    valor_nuevo={"status": "EXPIRED"},
                    actor_id=None,
                    actor_ip=None,
                )
                db.commit()
                count += 1
            except Exception:
                db.rollback()
                raise
    return count


@app.task(name="booking.cleanup_orphan_kyc_drafts")
def cleanup_orphan_kyc_drafts() -> int:
    """
    Elimina borradores KYC en disco/DB cuando todas las reservas del grupo están
    en EXPIRED o CANCELLED (idempotente; cubre cancelaciones sin pasar por TTL).
    """
    removed = 0
    with get_db_context(tenant_id=None, role="SUPERADMIN") as db:
        pairs = db.execute(
            select(
                ReservationDocument.tenant_id,
                ReservationDocument.group_event_id,
            ).distinct()
        ).all()
        for tid, gid in pairs:
            removed += purge_kyc_drafts_for_group_if_all_terminal(
                db, tenant_id=tid, group_event_id=gid
            )
        db.commit()
    return removed
