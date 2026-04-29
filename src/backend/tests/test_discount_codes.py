from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.modules.discounts.models import DiscountCode
from app.modules.discounts.services import (
    DiscountValidationError,
    compute_discount_amount,
    register_discount_usage,
    validate_code_for_subtotal,
)


def test_compute_discount_amount_percent_and_fixed():
    subtotal = Decimal("1000.00")
    assert compute_discount_amount(subtotal, "PERCENT", Decimal("10")) == Decimal("100.00")
    assert compute_discount_amount(subtotal, "FIXED", Decimal("2500")) == Decimal("1000.00")


def test_validate_discount_code_happy_path(db_super, tenant_a, user_a):
    code = DiscountCode(
        tenant_id=tenant_a.id,
        code="BLOQUE10",
        discount_type="PERCENT",
        discount_value=Decimal("10"),
        active=True,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db_super.add(code)
    db_super.commit()
    db_super.refresh(code)

    found, discount, total = validate_code_for_subtotal(
        db=db_super,
        tenant_id=tenant_a.id,
        user_id=user_a.id,
        code="bloque10",
        subtotal=Decimal("5000"),
    )
    assert found.id == code.id
    assert discount == Decimal("500.00")
    assert total == Decimal("4500.00")


def test_validate_discount_code_rejects_expired(db_super, tenant_a, user_a):
    code = DiscountCode(
        tenant_id=tenant_a.id,
        code="OLDCODE",
        discount_type="FIXED",
        discount_value=Decimal("1000"),
        active=True,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_super.add(code)
    db_super.commit()
    db_super.refresh(code)

    with pytest.raises(DiscountValidationError) as exc:
        validate_code_for_subtotal(
            db=db_super,
            tenant_id=tenant_a.id,
            user_id=user_a.id,
            code="OLDCODE",
            subtotal=Decimal("5000"),
        )
    assert exc.value.reason == "DISCOUNT_CODE_EXPIRED"


def test_single_use_per_user(db_super, tenant_a, user_a):
    code = DiscountCode(
        tenant_id=tenant_a.id,
        code="ONEUSER",
        discount_type="PERCENT",
        discount_value=Decimal("5"),
        active=True,
        single_use_per_user=True,
    )
    db_super.add(code)
    db_super.commit()
    db_super.refresh(code)

    _, discount, total = validate_code_for_subtotal(
        db=db_super,
        tenant_id=tenant_a.id,
        user_id=user_a.id,
        code="ONEUSER",
        subtotal=Decimal("1000"),
    )
    register_discount_usage(
        db=db_super,
        tenant_id=tenant_a.id,
        discount_code=code,
        user_id=user_a.id,
        subtotal=Decimal("1000"),
        discount_amount=discount,
        total=total,
        group_event_id=None,
        reservation_id=None,
    )
    db_super.commit()

    with pytest.raises(DiscountValidationError) as exc:
        validate_code_for_subtotal(
            db=db_super,
            tenant_id=tenant_a.id,
            user_id=user_a.id,
            code="ONEUSER",
            subtotal=Decimal("1000"),
        )
    assert exc.value.reason == "DISCOUNT_CODE_ALREADY_USED_BY_USER"
