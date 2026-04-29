"""E2E tests: full CRM flow (lead -> quote -> status -> download PDF)."""

from datetime import date, time

import pytest
from fastapi.testclient import TestClient

from app.modules.crm.models import QuoteStatus


@pytest.mark.integration
def test_crm_flow_lead_quote_status_download(
    client: TestClient,
    token_b: str,
    tenant_b,
    db_super,
):
    """Create lead, create quote, PATCH status, GET download PDF. Uses COMMERCIAL token (token_b)."""
    from app.modules.inventory.models import Space

    space = Space(
        tenant_id=tenant_b.id,
        name="Sala E2E",
        slug="sala-e2e-crm",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)

    # Create lead
    r_lead = client.post(
        "/api/leads",
        headers={"Authorization": f"Bearer {token_b}"},
        json={
            "name": "Cliente E2E",
            "email": "e2e@test.com",
            "phone": "+525500000000",
        },
    )
    assert r_lead.status_code == 201
    lead_id = r_lead.json()["id"]

    # Create quote
    r_quote = client.post(
        "/api/quotes",
        headers={"Authorization": f"Bearer {token_b}"},
        json={
            "lead_id": lead_id,
            "items": [
                {
                    "space_id": str(space.id),
                    "fecha": "2026-12-15",
                    "hora_inicio": "10:00:00",
                    "hora_fin": "12:00:00",
                    "precio": 200,
                },
            ],
        },
    )
    assert r_quote.status_code == 201
    data_quote = r_quote.json()
    quote_id = data_quote["id"]
    assert data_quote["status"] == QuoteStatus.DRAFT.value
    assert data_quote["total"] == 200
    assert len(data_quote["items"]) == 1

    # PATCH status: DRAFT -> SENT
    r_patch = client.patch(
        f"/api/quotes/{quote_id}/status",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"status": QuoteStatus.SENT.value},
    )
    assert r_patch.status_code == 204

    r_get = client.get(
        f"/api/quotes/{quote_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r_get.status_code == 200
    assert r_get.json()["status"] == QuoteStatus.SENT.value

    # Download PDF
    r_download = client.get(
        f"/api/quotes/{quote_id}/download",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r_download.status_code == 200
    assert r_download.headers["content-type"] == "application/pdf"
    assert r_download.content.startswith(b"%PDF")
    assert len(r_download.content) > 200
