"""Integration tests for event-based reservation creation."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_create_event_reservation_multiple_spaces_same_event(
    client: TestClient,
    token_a: str,
    tenant_a,
    db_super,
):
    from app.modules.inventory.models import Space
    from app.modules.pricing.models import PricingRule

    suf = uuid4().hex[:10]
    event_day = (date.today() + timedelta(days=365)).isoformat()
    space_a = Space(
        tenant_id=tenant_a.id,
        name="Auditorio Evento",
        slug=f"auditorio-evento-{suf}",
        capacidad_maxima=300,
        precio_por_hora=1200,
    )
    space_b = Space(
        tenant_id=tenant_a.id,
        name="Lobby Evento",
        slug=f"lobby-evento-{suf}",
        capacidad_maxima=180,
        precio_por_hora=900,
    )
    db_super.add_all([space_a, space_b])
    db_super.commit()
    db_super.refresh(space_a)
    db_super.refresh(space_b)

    for sp in (space_a, space_b):
        db_super.add(
            PricingRule(
                tenant_id=tenant_a.id,
                space_id=sp.id,
                base_6h=Decimal("100.0000"),
                base_12h=Decimal("180.0000"),
                extra_hour_rate=Decimal("20.0000"),
                discount_threshold=Decimal("0"),
                effective_from=date(2025, 1, 1),
                effective_to=None,
            )
        )
    db_super.commit()

    payload = {
        "event_name": "Congreso Educación",
        "items": [
            {
                "space_id": str(space_a.id),
                "fecha": event_day,
                "hora_inicio": "10:00:00",
                "hora_fin": "12:00:00",
            },
            {
                "space_id": str(space_b.id),
                "fecha": event_day,
                "hora_inicio": "10:00:00",
                "hora_fin": "12:00:00",
            },
        ],
    }

    response = client.post(
        "/api/reservation-events",
        headers={"Authorization": f"Bearer {token_a}"},
        json=payload,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["event_name"] == "Congreso Educación"
    assert len(data["reservations"]) == 2
    assert data["group_event_id"] is not None
    assert all(r["group_event_id"] == data["group_event_id"] for r in data["reservations"])
    assert all(r["event_name"] == "Congreso Educación" for r in data["reservations"])
