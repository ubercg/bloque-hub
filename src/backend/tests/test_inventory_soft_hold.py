"""Tests for SOFT_HOLD apply/release in inventory (quote-backed hold)."""

from datetime import date, time
from uuid import uuid4

import pytest

from app.modules.booking.services import create_reservation
from app.modules.inventory.models import Inventory, SlotStatus, Space
from app.modules.inventory.services import (
    SlotNotAvailableError,
    apply_soft_hold_for_quote,
    release_soft_hold_for_quote,
)


@pytest.mark.integration
def test_apply_and_release_soft_hold(tenant_a, db_super):
    """Apply SOFT_HOLD for a quote on two slots; then release; verify state."""
    space = Space(
        tenant_id=tenant_a.id,
        name="Sala Soft",
        slug="sala-soft-hold",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)

    quote_id = uuid4()
    slots = [
        (space.id, date(2026, 8, 1), time(10, 0), time(12, 0)),
        (space.id, date(2026, 8, 1), time(14, 0), time(16, 0)),
    ]
    apply_soft_hold_for_quote(quote_id, slots, tenant_a.id, db_super)
    db_super.commit()

    rows = (
        db_super.query(Inventory)
        .filter(
            Inventory.space_id == space.id,
            Inventory.fecha == date(2026, 8, 1),
        )
        .all()
    )
    assert len(rows) == 2
    for row in rows:
        assert row.estado == SlotStatus.SOFT_HOLD
        assert row.quote_id == quote_id

    release_soft_hold_for_quote(quote_id, db_super)
    db_super.commit()

    for row in rows:
        db_super.refresh(row)
    for row in rows:
        assert row.estado == SlotStatus.AVAILABLE
        assert row.quote_id is None


@pytest.mark.integration
def test_apply_soft_hold_when_slot_not_available_raises(tenant_a, user_a, db_super):
    """If one slot is already TTL_BLOCKED (e.g. by a reservation), apply_soft_hold_for_quote raises SlotNotAvailableError."""
    space = Space(
        tenant_id=tenant_a.id,
        name="Sala Conflict",
        slug="sala-conflict-hold",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)

    # Claim the slot via a real reservation (TTL_BLOCKED + reservation_id)
    create_reservation(
        tenant_id=tenant_a.id,
        user_id=user_a.id,
        space_id=space.id,
        fecha=date(2026, 9, 1),
        hora_inicio=time(10, 0),
        hora_fin=time(12, 0),
        db=db_super,
    )
    db_super.commit()

    slot_row = (
        db_super.query(Inventory)
        .filter(
            Inventory.space_id == space.id,
            Inventory.fecha == date(2026, 9, 1),
            Inventory.hora_inicio == time(10, 0),
        )
        .first()
    )
    assert slot_row is not None
    assert slot_row.estado == SlotStatus.TTL_BLOCKED

    quote_id = uuid4()
    slots = [
        (space.id, date(2026, 9, 1), time(10, 0), time(12, 0)),
    ]
    with pytest.raises(SlotNotAvailableError):
        apply_soft_hold_for_quote(quote_id, slots, tenant_a.id, db_super)
    db_super.rollback()

    db_super.refresh(slot_row)
    assert slot_row.estado == SlotStatus.TTL_BLOCKED
    assert slot_row.quote_id is None
