"""Unit tests for Quote state machine (transitions)."""

import pytest

from app.modules.crm.models import Quote, QuoteStatus
from app.modules.crm.services import (
    InvalidQuoteTransitionError,
    transition_quote_status,
)


@pytest.mark.integration
def test_valid_transitions(tenant_a, db_super):
    """DRAFT -> SENT and SENT -> APPROVED are allowed."""
    from app.modules.crm.models import Lead

    lead = Lead(
        tenant_id=tenant_a.id,
        name="Lead State",
        email="state@test.com",
    )
    db_super.add(lead)
    db_super.commit()
    db_super.refresh(lead)

    quote = Quote(
        tenant_id=tenant_a.id,
        lead_id=lead.id,
        status=QuoteStatus.DRAFT,
        total=0,
    )
    db_super.add(quote)
    db_super.commit()
    db_super.refresh(quote)

    transition_quote_status(quote, QuoteStatus.SENT, db_super)
    db_super.commit()
    db_super.refresh(quote)
    assert quote.status == QuoteStatus.SENT

    transition_quote_status(quote, QuoteStatus.APPROVED, db_super)
    db_super.commit()
    db_super.refresh(quote)
    assert quote.status == QuoteStatus.APPROVED


@pytest.mark.integration
def test_invalid_transition_approved_to_draft(tenant_a, db_super):
    """APPROVED -> DRAFT is not allowed."""
    from app.modules.crm.models import Lead

    lead = Lead(
        tenant_id=tenant_a.id,
        name="Lead Invalid",
        email="invalid@test.com",
    )
    db_super.add(lead)
    db_super.commit()
    db_super.refresh(lead)

    quote = Quote(
        tenant_id=tenant_a.id,
        lead_id=lead.id,
        status=QuoteStatus.APPROVED,
        total=0,
    )
    db_super.add(quote)
    db_super.commit()
    db_super.refresh(quote)

    with pytest.raises(InvalidQuoteTransitionError):
        transition_quote_status(quote, QuoteStatus.DRAFT, db_super)


@pytest.mark.integration
def test_invalid_transition_sent_to_draft(tenant_a, db_super):
    """SENT -> DRAFT is not allowed."""
    from app.modules.crm.models import Lead

    lead = Lead(
        tenant_id=tenant_a.id,
        name="Lead Sent",
        email="sent@test.com",
    )
    db_super.add(lead)
    db_super.commit()
    db_super.refresh(lead)

    quote = Quote(
        tenant_id=tenant_a.id,
        lead_id=lead.id,
        status=QuoteStatus.SENT,
        total=0,
    )
    db_super.add(quote)
    db_super.commit()
    db_super.refresh(quote)

    with pytest.raises(InvalidQuoteTransitionError):
        transition_quote_status(quote, QuoteStatus.DRAFT, db_super)
