"""Integration tests: create_quote with SOFT_HOLD (atomic)."""

from datetime import date, time

import pytest

from app.modules.crm.models import Lead, Quote
from app.modules.crm.schemas import QuoteItemCreate
from app.modules.crm.services import create_quote
from app.modules.inventory.models import Inventory, SlotStatus
from app.modules.inventory.services import SlotNotAvailableError


@pytest.mark.integration
def test_create_quote_applies_soft_hold(tenant_a, db_super):
    """When all slots are available, quote is created and SOFT_HOLD applied on inventory."""
    from app.modules.inventory.models import Space

    space1 = Space(
        tenant_id=tenant_a.id,
        name="Sala A",
        slug="sala-a-quote",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    space2 = Space(
        tenant_id=tenant_a.id,
        name="Sala B",
        slug="sala-b-quote",
        capacidad_maxima=5,
        precio_por_hora=50,
    )
    db_super.add_all([space1, space2])
    db_super.commit()
    db_super.refresh(space1)
    db_super.refresh(space2)

    lead = Lead(
        tenant_id=tenant_a.id,
        name="Cliente Quote",
        email="quote@test.com",
    )
    db_super.add(lead)
    db_super.commit()
    db_super.refresh(lead)

    items = [
        QuoteItemCreate(
            space_id=space1.id,
            fecha=date(2026, 11, 1),
            hora_inicio=time(10, 0),
            hora_fin=time(12, 0),
            precio=200,
        ),
        QuoteItemCreate(
            space_id=space2.id,
            fecha=date(2026, 11, 1),
            hora_inicio=time(14, 0),
            hora_fin=time(16, 0),
            precio=100,
        ),
    ]
    quote = create_quote(
        tenant_id=tenant_a.id,
        lead_id=lead.id,
        items=items,
        discount_pct=None,
        discount_amount=None,
        discount_justification=None,
        db=db_super,
    )
    db_super.commit()
    db_super.refresh(quote)

    assert quote.id is not None
    assert quote.status.value == "DRAFT"
    assert quote.total == 300
    assert len(quote.items) == 2

    slots = (
        db_super.query(Inventory)
        .filter(Inventory.quote_id == quote.id)
        .all()
    )
    assert len(slots) == 2
    for slot in slots:
        assert slot.estado == SlotStatus.SOFT_HOLD
        assert slot.quote_id == quote.id


@pytest.mark.integration
def test_create_quote_rollback_when_slot_unavailable(tenant_a, user_a, db_super):
    """When one slot is already taken, SlotNotAvailableError and no quote/SOFT_HOLD created."""
    from app.modules.booking.services import create_reservation
    from app.modules.inventory.models import Space

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala Unica",
        slug="sala-unica-quote",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)

    create_reservation(
        tenant_id=tenant_a.id,
        user_id=user_a.id,
        space_id=space.id,
        fecha=date(2026, 12, 1),
        hora_inicio=time(10, 0),
        hora_fin=time(12, 0),
        db=db_super,
    )
    db_super.commit()

    lead = Lead(
        tenant_id=tenant_a.id,
        name="Cliente Conflict",
        email="conflict@test.com",
    )
    db_super.add(lead)
    db_super.commit()
    db_super.refresh(lead)

    items = [
        QuoteItemCreate(
            space_id=space.id,
            fecha=date(2026, 12, 1),
            hora_inicio=time(10, 0),
            hora_fin=time(12, 0),
            precio=200,
        ),
    ]
    with pytest.raises(SlotNotAvailableError):
        create_quote(
            tenant_id=tenant_a.id,
            lead_id=lead.id,
            items=items,
            discount_pct=None,
            discount_amount=None,
            discount_justification=None,
            db=db_super,
        )
    db_super.rollback()

    # No quote for this lead with that slot
    count = db_super.query(Quote).filter(Quote.lead_id == lead.id).count()
    assert count == 0

    slot = (
        db_super.query(Inventory)
        .filter(
            Inventory.space_id == space.id,
            Inventory.fecha == date(2026, 12, 1),
            Inventory.hora_inicio == time(10, 0),
        )
        .first()
    )
    assert slot is not None
    assert slot.estado == SlotStatus.TTL_BLOCKED
    assert slot.quote_id is None
