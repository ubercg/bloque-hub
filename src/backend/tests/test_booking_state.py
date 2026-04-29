"""Unit tests: BookingStateService transitions and InvalidStateTransitionError."""

import uuid
from datetime import date, time

import pytest
from sqlalchemy.orm import Session

from app.modules.booking.models import Reservation, ReservationStatus
from app.modules.booking.services import (
    InvalidStateTransitionError,
    can_cancel_reservation,
    cancel_reservation,
    confirm_payment,
    reject_payment,
    transition_to_awaiting_payment,
    transition_to_payment_under_review,
)


def _make_reservation(
    db: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    space_id: uuid.UUID,
    status: ReservationStatus = ReservationStatus.PENDING_SLIP,
) -> Reservation:
    r = Reservation(
        tenant_id=tenant_id,
        user_id=user_id,
        space_id=space_id,
        fecha=date(2026, 6, 1),
        hora_inicio=time(10, 0),
        hora_fin=time(12, 0),
        status=status,
    )
    db.add(r)
    db.flush()
    return r


@pytest.mark.integration
def test_transition_pending_to_awaiting_payment(tenant_a, user_a, db_super: Session):
    from app.modules.inventory.models import Space

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala",
        slug="sala-booking-state",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space)
    db_super.flush()
    r = _make_reservation(db_super, tenant_a.id, user_a.id, space.id)
    transition_to_awaiting_payment(r, db_super)
    assert r.status == ReservationStatus.AWAITING_PAYMENT


@pytest.mark.integration
def test_invalid_transition_pending_to_confirmed(tenant_a, user_a, db_super: Session):
    from app.modules.inventory.models import Space

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala2",
        slug="sala2-booking-state",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space)
    db_super.flush()
    r = _make_reservation(db_super, tenant_a.id, user_a.id, space.id)
    with pytest.raises(InvalidStateTransitionError):
        confirm_payment(r, db_super)


@pytest.mark.integration
def test_invalid_transition_pending_to_payment_under_review(tenant_a, user_a, db_super: Session):
    from app.modules.inventory.models import Space

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala3",
        slug="sala3-booking-state",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space)
    db_super.flush()
    r = _make_reservation(db_super, tenant_a.id, user_a.id, space.id)
    with pytest.raises(InvalidStateTransitionError):
        transition_to_payment_under_review(r, db_super)


@pytest.mark.integration
def test_confirm_payment_dispatcher_rollback(tenant_a, user_a, db_super: Session):
    """When dispatcher raises, state must not persist (caller does rollback)."""
    from app.modules.booking.services import EventDispatcher
    from app.modules.inventory.models import Inventory, SlotStatus, Space
    from app.db.session import get_db_context

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala4",
        slug="sala4-booking-state",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space)
    db_super.flush()
    r = _make_reservation(
        db_super, tenant_a.id, user_a.id, space.id, status=ReservationStatus.PAYMENT_UNDER_REVIEW
    )
    slot = Inventory(
        space_id=space.id,
        tenant_id=tenant_a.id,
        fecha=r.fecha,
        hora_inicio=r.hora_inicio,
        hora_fin=r.hora_fin,
        estado=SlotStatus.TTL_BLOCKED,
        reservation_id=r.id,
    )
    db_super.add(slot)
    db_super.commit()
    reservation_id = r.id
    space_id = space.id

    r = db_super.query(Reservation).filter(Reservation.id == reservation_id).first()
    assert r is not None

    class FailingDispatcher(EventDispatcher):
        def on_reservation_confirmed(self, reservation: Reservation, db) -> None:
            raise RuntimeError("Simulated failure")

    with pytest.raises(RuntimeError):
        confirm_payment(r, db_super, event_dispatcher=FailingDispatcher())
    db_super.rollback()

    # Verify DB was not updated: query in a new session
    with get_db_context(tenant_id=None, role="SUPERADMIN") as db2:
        from app.modules.booking.models import Reservation as ReservationModel
        from app.modules.inventory.models import Inventory as InventoryModel
        res_after = db2.query(ReservationModel).filter(ReservationModel.id == reservation_id).first()
        slot_after = (
            db2.query(InventoryModel)
            .filter(InventoryModel.space_id == space_id, InventoryModel.reservation_id == reservation_id)
            .first()
        )
        assert res_after is not None and res_after.status == ReservationStatus.PAYMENT_UNDER_REVIEW
        assert slot_after is not None and slot_after.estado == SlotStatus.TTL_BLOCKED


# --- cancel_reservation / can_cancel_reservation ---


@pytest.mark.integration
def test_can_cancel_reservation_only_pending_or_awaiting():
    """can_cancel_reservation is True only for PENDING_SLIP and AWAITING_PAYMENT."""
    assert can_cancel_reservation(ReservationStatus.PENDING_SLIP) is True
    assert can_cancel_reservation(ReservationStatus.AWAITING_PAYMENT) is True
    assert can_cancel_reservation(ReservationStatus.PAYMENT_UNDER_REVIEW) is False
    assert can_cancel_reservation(ReservationStatus.CONFIRMED) is False
    assert can_cancel_reservation(ReservationStatus.EXPIRED) is False
    assert can_cancel_reservation(ReservationStatus.CANCELLED) is False


@pytest.mark.integration
def test_cancel_reservation_pending_slip_releases_slot(tenant_a, user_a, db_super: Session):
    """cancel_reservation from PENDING_SLIP sets CANCELLED and releases inventory slot."""
    from app.modules.inventory.models import Inventory, SlotStatus, Space

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala Cancel",
        slug="sala-cancel-booking-state",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space)
    db_super.flush()
    r = _make_reservation(db_super, tenant_a.id, user_a.id, space.id, status=ReservationStatus.PENDING_SLIP)
    slot = Inventory(
        space_id=space.id,
        tenant_id=tenant_a.id,
        fecha=r.fecha,
        hora_inicio=r.hora_inicio,
        hora_fin=r.hora_fin,
        estado=SlotStatus.TTL_BLOCKED,
        reservation_id=r.id,
    )
    db_super.add(slot)
    db_super.commit()
    db_super.refresh(r)
    db_super.refresh(slot)

    cancel_reservation(r, db_super)
    db_super.commit()

    db_super.refresh(r)
    db_super.refresh(slot)
    assert r.status == ReservationStatus.CANCELLED
    assert slot.estado == SlotStatus.AVAILABLE
    assert slot.reservation_id is None


@pytest.mark.integration
def test_cancel_reservation_awaiting_payment_succeeds(tenant_a, user_a, db_super: Session):
    """cancel_reservation from AWAITING_PAYMENT sets CANCELLED and releases slot."""
    from app.modules.inventory.models import Inventory, SlotStatus, Space

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala Cancel Await",
        slug="sala-cancel-await-booking-state",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space)
    db_super.flush()
    r = _make_reservation(db_super, tenant_a.id, user_a.id, space.id, status=ReservationStatus.AWAITING_PAYMENT)
    slot = Inventory(
        space_id=space.id,
        tenant_id=tenant_a.id,
        fecha=r.fecha,
        hora_inicio=r.hora_inicio,
        hora_fin=r.hora_fin,
        estado=SlotStatus.TTL_BLOCKED,
        reservation_id=r.id,
    )
    db_super.add(slot)
    db_super.commit()
    db_super.refresh(r)

    cancel_reservation(r, db_super)
    db_super.commit()

    db_super.refresh(r)
    db_super.refresh(slot)
    assert r.status == ReservationStatus.CANCELLED
    assert slot.estado == SlotStatus.AVAILABLE
    assert slot.reservation_id is None


@pytest.mark.integration
def test_cancel_reservation_confirmed_raises(tenant_a, user_a, db_super: Session):
    """cancel_reservation from CONFIRMED raises InvalidStateTransitionError."""
    from app.modules.inventory.models import Space

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala Cancel No",
        slug="sala-cancel-no-booking-state",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space)
    db_super.flush()
    r = _make_reservation(db_super, tenant_a.id, user_a.id, space.id, status=ReservationStatus.CONFIRMED)

    with pytest.raises(InvalidStateTransitionError):
        cancel_reservation(r, db_super)
