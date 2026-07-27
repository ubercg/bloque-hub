"""Public anonymous discount validation for REQ-012 wizard Step 2."""

from decimal import Decimal

import pytest

from app.core.config import settings
from app.modules.discounts.models import DiscountCode


def _set_default_tenant(monkeypatch, tenant_id):
    monkeypatch.setattr(settings, "DEFAULT_TENANT_ID", str(tenant_id))


def _seed_code(db_super, tenant_id, code: str = "BLOQUE10") -> DiscountCode:
    row = DiscountCode(
        tenant_id=tenant_id,
        code=code,
        discount_type="PERCENT",
        discount_value=Decimal("10.0000"),
        min_subtotal=Decimal("1000.0000"),
        max_uses=None,
        used_count=0,
        active=True,
        expires_at=None,
        single_use_per_user=False,
        description="test",
        created_by=None,
    )
    db_super.add(row)
    db_super.commit()
    db_super.refresh(row)
    return row


@pytest.mark.integration
class TestPublicValidateDiscount:
    def test_valid_code_without_auth(self, client, monkeypatch, tenant_a, db_super):
        _set_default_tenant(monkeypatch, tenant_a.id)
        _seed_code(db_super, tenant_a.id)

        response = client.post(
            "/api/public/quote-requests/validate-discount",
            json={"code": "bloque10", "subtotal": 5000},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["valid"] is True
        assert body["code"] == "BLOQUE10"
        assert Decimal(str(body["discount_amount"])) == Decimal("500.00")
        assert Decimal(str(body["total"])) == Decimal("4500.00")

    def test_invalid_code_returns_valid_false(self, client, monkeypatch, tenant_a):
        _set_default_tenant(monkeypatch, tenant_a.id)

        response = client.post(
            "/api/public/quote-requests/validate-discount",
            json={"code": "NOEXISTE", "subtotal": 5000},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["valid"] is False
        assert body["reason"] == "DISCOUNT_CODE_INVALID"

    def test_min_subtotal_not_met(self, client, monkeypatch, tenant_a, db_super):
        _set_default_tenant(monkeypatch, tenant_a.id)
        _seed_code(db_super, tenant_a.id, code="MINTEST")

        response = client.post(
            "/api/public/quote-requests/validate-discount",
            json={"code": "MINTEST", "subtotal": 100},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["valid"] is False
        assert body["reason"] == "DISCOUNT_CODE_MIN_SUBTOTAL_NOT_MET"
