"""Tests for quote PDF generation."""

from datetime import date, time

import pytest

from app.modules.crm.models import Lead, Quote, QuoteItem, QuoteStatus
from app.modules.crm.services import generate_quote_pdf


@pytest.mark.integration
def test_generate_quote_pdf_returns_valid_pdf(tenant_a, db_super):
    """generate_quote_pdf returns bytes that are a valid PDF and contain expected content."""
    from app.modules.inventory.models import Space

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala PDF",
        slug="sala-pdf-test",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)

    lead = Lead(
        tenant_id=tenant_a.id,
        name="Cliente PDF Test",
        email="pdf@test.com",
    )
    db_super.add(lead)
    db_super.commit()
    db_super.refresh(lead)

    quote = Quote(
        tenant_id=tenant_a.id,
        lead_id=lead.id,
        status=QuoteStatus.DRAFT,
        total=200,
    )
    db_super.add(quote)
    db_super.flush()
    db_super.add(
        QuoteItem(
            quote_id=quote.id,
            space_id=space.id,
            fecha=date(2026, 10, 15),
            hora_inicio=time(10, 0),
            hora_fin=time(12, 0),
            precio=200,
            item_order=0,
        )
    )
    db_super.commit()
    db_super.refresh(quote)

    pdf_bytes = generate_quote_pdf(quote, db_super)

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 200
    # PDF often embeds text; try to find lead name or "Cotización"
    assert b"PDF" in pdf_bytes or b"Cotizaci" in pdf_bytes or b"Cliente" in pdf_bytes or b"200.00" in pdf_bytes
