"""Integration tests for Contract (send-contract, webhook, delegate signer)."""

from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.core.config import settings
from app.db.session import get_db_context
from app.modules.crm.models import Contract, ContractStatus, Lead, Quote, QuoteItem, QuoteStatus
from app.modules.crm.services import send_contract_for_signature
from app.modules.crm.tasks import add_delegate_signer
from app.modules.inventory.models import Space


@pytest.mark.integration
def test_send_contract_creates_contract_with_provider_id(tenant_a, db_super):
    """POST send-contract with APPROVED quote creates Contract with provider_document_id (mock)."""
    space = Space(
        tenant_id=tenant_a.id,
        name="Sala Contract",
        slug="sala-contract-test",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)

    lead = Lead(
        tenant_id=tenant_a.id,
        name="Cliente Contract",
        email="contract@test.com",
    )
    db_super.add(lead)
    db_super.commit()
    db_super.refresh(lead)

    quote = Quote(
        tenant_id=tenant_a.id,
        lead_id=lead.id,
        status=QuoteStatus.APPROVED,
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

    contract = send_contract_for_signature(
        quote, callback_url="http://test/api/webhooks/fea", db=db_super
    )
    db_super.commit()
    db_super.refresh(contract)

    assert contract.id is not None
    assert contract.quote_id == quote.id
    assert contract.tenant_id == tenant_a.id
    assert contract.status == ContractStatus.SENT
    assert contract.provider_document_id is not None
    assert len(contract.provider_document_id) == 36  # UUID string
    assert contract.sent_at is not None
    assert contract.fea_provider == "mock"


@pytest.mark.integration
def test_webhook_signed_updates_contract_and_stores_pdf(tenant_a, db_super, monkeypatch):
    """Webhook with event signed updates Contract to SIGNED and stores PDF on filesystem."""
    monkeypatch.setattr(settings, "FEA_SKIP_HMAC_IN_TESTS", True)
    monkeypatch.setattr(settings, "CONTRACTS_STORAGE_PATH", "data/contracts_test")

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala Webhook",
        slug="sala-webhook-test",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)
    lead = Lead(tenant_id=tenant_a.id, name="Lead Webhook", email="webhook@test.com")
    db_super.add(lead)
    db_super.commit()
    db_super.refresh(lead)
    quote = Quote(
        tenant_id=tenant_a.id,
        lead_id=lead.id,
        status=QuoteStatus.APPROVED,
        total=100,
    )
    db_super.add(quote)
    db_super.flush()
    db_super.add(
        QuoteItem(
            quote_id=quote.id,
            space_id=space.id,
            fecha=date(2026, 11, 1),
            hora_inicio=time(9, 0),
            hora_fin=time(10, 0),
            precio=100,
            item_order=0,
        )
    )
    db_super.commit()
    db_super.refresh(quote)

    contract = send_contract_for_signature(
        quote, callback_url="http://test/api/webhooks/fea", db=db_super
    )
    db_super.commit()
    db_super.refresh(contract)
    provider_document_id = contract.provider_document_id

    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    r = client.post(
        "/api/webhooks/fea",
        json={"provider_document_id": provider_document_id, "event": "signed"},
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 204

    signed_url = None
    with get_db_context(tenant_id=None, role="SUPERADMIN") as db:
        c = db.query(Contract).filter(Contract.id == contract.id).first()
        assert c is not None
        assert c.status == ContractStatus.SIGNED
        assert c.signed_document_url is not None
        assert c.signed_document_url.endswith("_signed.pdf")
        signed_url = c.signed_document_url

    from pathlib import Path
    storage = Path(settings.CONTRACTS_STORAGE_PATH)
    path = storage / signed_url
    assert path.is_file()
    assert path.read_bytes().startswith(b"%PDF")


@pytest.mark.integration
def test_e2e_send_contract_and_get_contract(tenant_a, db_super, client, token_commercial_a):
    """E2E: create APPROVED quote, POST send-contract, GET quote contract."""
    from app.modules.inventory.models import Space

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala E2E",
        slug="sala-e2e-contract",
        capacidad_maxima=10,
        precio_por_hora=80,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)
    lead = Lead(tenant_id=tenant_a.id, name="E2E Lead", email="e2e@test.com")
    db_super.add(lead)
    db_super.commit()
    db_super.refresh(lead)
    quote = Quote(
        tenant_id=tenant_a.id,
        lead_id=lead.id,
        status=QuoteStatus.APPROVED,
        total=80,
    )
    db_super.add(quote)
    db_super.flush()
    db_super.add(
        QuoteItem(
            quote_id=quote.id,
            space_id=space.id,
            fecha=date(2026, 12, 1),
            hora_inicio=time(14, 0),
            hora_fin=time(15, 0),
            precio=80,
            item_order=0,
        )
    )
    db_super.commit()
    db_super.refresh(quote)

    r = client.post(
        f"/api/quotes/{quote.id}/send-contract",
        headers={"Authorization": f"Bearer {token_commercial_a}"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["quote_id"] == str(quote.id)
    assert data["status"] == "sent"
    assert data["provider_document_id"] is not None

    r2 = client.get(
        f"/api/quotes/{quote.id}/contract",
        headers={"Authorization": f"Bearer {token_commercial_a}"},
    )
    assert r2.status_code == 200
    assert r2.json()["id"] == data["id"]


@pytest.mark.integration
def test_add_delegate_signer_task_sets_delegate_activated(tenant_a, db_super):
    """Task add_delegate_signer marks contract with sent_at > 24h and no delegate yet."""
    lead = Lead(tenant_id=tenant_a.id, name="Lead Delegate", email="delegate@test.com")
    db_super.add(lead)
    db_super.commit()
    db_super.refresh(lead)
    quote = Quote(
        tenant_id=tenant_a.id,
        lead_id=lead.id,
        status=QuoteStatus.APPROVED,
        total=50,
    )
    db_super.add(quote)
    db_super.commit()
    db_super.refresh(quote)

    contract = Contract(
        tenant_id=tenant_a.id,
        quote_id=quote.id,
        status=ContractStatus.SENT,
        provider_document_id="mock-doc-delegate-123",
        sent_at=datetime.now(timezone.utc) - timedelta(hours=25),
        delegate_signer_activated_at=None,
    )
    db_super.add(contract)
    db_super.commit()
    db_super.refresh(contract)

    n = add_delegate_signer()
    assert n == 1

    with get_db_context(tenant_id=None, role="SUPERADMIN") as db:
        c = db.query(Contract).filter(Contract.id == contract.id).first()
        assert c is not None
        assert c.delegate_signer_activated_at is not None
