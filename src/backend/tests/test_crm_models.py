"""Unit tests for CRM models: Lead and Quote creation/retrieval."""

from datetime import date, time

import pytest

from app.modules.crm.models import Lead, Quote, QuoteItem, QuoteStatus


@pytest.mark.integration
def test_lead_and_quote_creation_and_retrieval(tenant_a, db_super):
    """Create Lead and Quote with items; verify relationships and types."""
    from app.modules.inventory.models import Space

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala CRM",
        slug="sala-crm-test",
        capacidad_maxima=20,
        precio_por_hora=500,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)

    lead = Lead(
        tenant_id=tenant_a.id,
        name="Cliente Test",
        email="cliente@test.com",
        phone="+525512345678",
        company="Acme SA",
    )
    db_super.add(lead)
    db_super.commit()
    db_super.refresh(lead)

    quote = Quote(
        tenant_id=tenant_a.id,
        lead_id=lead.id,
        status=QuoteStatus.DRAFT,
        total=1000,
    )
    db_super.add(quote)
    db_super.flush()

    item1 = QuoteItem(
        quote_id=quote.id,
        space_id=space.id,
        fecha=date(2026, 10, 1),
        hora_inicio=time(10, 0),
        hora_fin=time(12, 0),
        precio=500,
        item_order=0,
    )
    item2 = QuoteItem(
        quote_id=quote.id,
        space_id=space.id,
        fecha=date(2026, 10, 1),
        hora_inicio=time(14, 0),
        hora_fin=time(16, 0),
        precio=500,
        item_order=1,
    )
    db_super.add_all([item1, item2])
    db_super.commit()
    db_super.refresh(quote)
    db_super.refresh(lead)

    assert lead.id is not None
    assert lead.name == "Cliente Test"
    assert lead.tenant_id == tenant_a.id

    assert quote.id is not None
    assert quote.lead_id == lead.id
    assert quote.status == QuoteStatus.DRAFT
    assert quote.total == 1000
    assert len(quote.items) == 2
    assert quote.items[0].space_id == space.id
    assert quote.items[0].precio == 500
    assert quote.items[1].item_order == 1
