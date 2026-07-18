"""Integration tests for the public price-preview endpoint (REQ-012, PR#6b).

`POST /api/public/quote-requests/price-preview` — public (no JWT), advisory
pricing preview for wizard Step 2 (design.md §6.6). The authoritative price is
always recomputed server-side at submit; this endpoint exists only because an
anonymous client cannot call the JWT-protected `/quotes/calculate` or
`/pricing-rules` endpoints to render `cotizacionCalculada` before submit.
"""

from datetime import date, time, timedelta
from decimal import Decimal

import pytest

from app.core.config import settings
from app.db.session import get_db_context
from app.modules.crm.public_service import _duration_hours
from app.modules.inventory.models import Space
from app.modules.pricing.models import PricingRule
from app.modules.pricing.services import calculate_price


def _make_space(db_super, tenant_id, suffix: str) -> Space:
    space = Space(
        tenant_id=tenant_id,
        name=f"Space {suffix}",
        slug=f"space-{suffix}",
        capacidad_maxima=100,
        precio_por_hora=500,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)
    return space


def _make_pricing_rule(db_super, tenant_id, space_id) -> None:
    db_super.add(
        PricingRule(
            tenant_id=tenant_id,
            space_id=space_id,
            base_6h=Decimal("100.0000"),
            base_12h=Decimal("180.0000"),
            extra_hour_rate=Decimal("20.0000"),
            discount_threshold=Decimal("0"),
            effective_from=date(2025, 1, 1),
            effective_to=None,
        )
    )
    db_super.commit()


def _item_dict(space_id, fecha, hora_inicio="10:00:00", hora_fin="12:00:00") -> dict:
    return {
        "space_id": str(space_id),
        "fecha": fecha.isoformat(),
        "hora_inicio": hora_inicio,
        "hora_fin": hora_fin,
    }


def _set_default_tenant(monkeypatch, tenant_id):
    monkeypatch.setattr(settings, "DEFAULT_TENANT_ID", str(tenant_id))


@pytest.mark.integration
class TestPublicPricePreview:
    def test_single_item_returns_computed_price(
        self, client, monkeypatch, tenant_a, db_super
    ):
        _set_default_tenant(monkeypatch, tenant_a.id)
        space = _make_space(db_super, tenant_a.id, "solo")
        _make_pricing_rule(db_super, tenant_a.id, space.id)
        day = date.today() + timedelta(days=70)

        response = client.post(
            "/api/public/quote-requests/price-preview",
            json={"items": [_item_dict(space.id, day)]},
        )

        assert response.status_code == 200
        body = response.json()

        duration_hours = _duration_hours(time(10, 0, 0), time(12, 0, 0), day)

        with get_db_context(tenant_id=str(tenant_a.id), role=None) as db:
            breakdown = calculate_price(
                space_id=space.id,
                duration_hours=duration_hours,
                tenant_id=tenant_a.id,
                target_date=day,
                db=db,
            )

        assert len(body["items"]) == 1
        assert Decimal(str(body["items"][0]["price"])) == breakdown.total_price
        assert Decimal(str(body["total"])) == breakdown.total_price

    def test_multi_item_aggregate_is_sum(self, client, monkeypatch, tenant_a, db_super):
        _set_default_tenant(monkeypatch, tenant_a.id)
        space_1 = _make_space(db_super, tenant_a.id, "multi1")
        space_2 = _make_space(db_super, tenant_a.id, "multi2")
        _make_pricing_rule(db_super, tenant_a.id, space_1.id)
        _make_pricing_rule(db_super, tenant_a.id, space_2.id)
        day = date.today() + timedelta(days=71)

        response = client.post(
            "/api/public/quote-requests/price-preview",
            json={
                "items": [
                    _item_dict(space_1.id, day),
                    _item_dict(space_2.id, day, "13:00:00", "19:00:00"),
                ]
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) == 2
        expected_total = sum(Decimal(str(i["price"])) for i in body["items"])
        assert Decimal(str(body["total"])) == expected_total

    def test_space_without_pricing_rule_returns_422(
        self, client, monkeypatch, tenant_a, db_super
    ):
        _set_default_tenant(monkeypatch, tenant_a.id)
        space = _make_space(db_super, tenant_a.id, "norule")
        day = date.today() + timedelta(days=72)

        response = client.post(
            "/api/public/quote-requests/price-preview",
            json={"items": [_item_dict(space.id, day)]},
        )

        assert response.status_code == 422
        assert response.json()["detail"]["reason"] == "NO_PRICING_RULE"

    def test_no_auth_header_required(self, client, monkeypatch, tenant_a, db_super):
        _set_default_tenant(monkeypatch, tenant_a.id)
        space = _make_space(db_super, tenant_a.id, "noauth")
        _make_pricing_rule(db_super, tenant_a.id, space.id)
        day = date.today() + timedelta(days=73)

        response = client.post(
            "/api/public/quote-requests/price-preview",
            json={"items": [_item_dict(space.id, day)]},
        )

        assert response.status_code == 200
