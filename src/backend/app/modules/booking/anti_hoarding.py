"""Anti-hoarding: limit active reservations per unverified user (CUSTOMER)."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import STAFF_ROLES
from app.modules.booking.models import Reservation, ReservationStatus

# States that count as "active" for the limit (pre-confirmation)
ACTIVE_STATUSES = (
    ReservationStatus.PENDING_SLIP,
    ReservationStatus.AWAITING_PAYMENT,
    ReservationStatus.PAYMENT_UNDER_REVIEW,
)
MAX_ACTIVE_RESERVATIONS_PER_CUSTOMER = 3


def count_active_reservations_for_user(
    db: Session,
    tenant_id: UUID,
    user_id: UUID,
) -> int:
    """
    Return the number of logical active reservations for this user.

    - Grouped event reservations count as one via group_event_id.
    - Single-space reservations (without group_event_id) count individually via id.
    """
    stmt = (
        select(
            func.count(
                func.distinct(
                    func.coalesce(Reservation.group_event_id, Reservation.id)
                )
            )
        )
        .where(Reservation.tenant_id == tenant_id)
        .where(Reservation.user_id == user_id)
        .where(Reservation.status.in_(ACTIVE_STATUSES))
    )
    return db.execute(stmt).scalar_one() or 0


def check_anti_hoarding(
    db: Session,
    tenant_id: UUID,
    user_id: UUID,
    role: str | None,
) -> None:
    """
    Raise if the user would exceed the active reservation limit.
    Only applies to non-staff roles (CUSTOMER). Staff roles are not limited.
    """
    if role in STAFF_ROLES:
        return
    count = count_active_reservations_for_user(db, tenant_id, user_id)
    if count >= MAX_ACTIVE_RESERVATIONS_PER_CUSTOMER:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=403,
            detail="Máximo 3 reservas activas; complete o cancele una antes de crear otra.",
        )
