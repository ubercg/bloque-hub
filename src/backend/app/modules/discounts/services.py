from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.discounts.models import DiscountCode, DiscountCodeUsage


class DiscountValidationError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def normalize_discount_code(code: str) -> str:
    return code.strip().upper()


def discount_status(code: DiscountCode) -> str:
    now = datetime.now(timezone.utc)
    if not code.active:
        return "INACTIVE"
    if code.expires_at is not None and code.expires_at < now:
        return "EXPIRED"
    if code.max_uses is not None and code.used_count >= code.max_uses:
        return "USAGE_LIMIT_REACHED"
    return "ACTIVE"


def compute_discount_amount(
    subtotal: Decimal, discount_type: str, discount_value: Decimal
) -> Decimal:
    if subtotal <= 0:
        return Decimal("0")
    if discount_type == "PERCENT":
        pct = max(Decimal("0"), min(discount_value, Decimal("100")))
        amount = (subtotal * pct / Decimal("100")).quantize(Decimal("0.01"))
    else:
        amount = discount_value.quantize(Decimal("0.01"))
    return min(amount, subtotal)


def get_code_for_tenant(db: Session, tenant_id: uuid.UUID, code: str) -> DiscountCode | None:
    normalized = normalize_discount_code(code)
    stmt = select(DiscountCode).where(
        DiscountCode.tenant_id == tenant_id,
        func.upper(DiscountCode.code) == normalized,
    )
    return db.execute(stmt).scalars().first()


def validate_code_for_subtotal(
    db: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    code: str,
    subtotal: Decimal,
) -> tuple[DiscountCode, Decimal, Decimal]:
    discount_code = get_code_for_tenant(db, tenant_id, code)
    if discount_code is None:
        raise DiscountValidationError("DISCOUNT_CODE_INVALID")

    status = discount_status(discount_code)
    if status == "INACTIVE":
        raise DiscountValidationError("DISCOUNT_CODE_INACTIVE")
    if status == "EXPIRED":
        raise DiscountValidationError("DISCOUNT_CODE_EXPIRED")
    if status == "USAGE_LIMIT_REACHED":
        raise DiscountValidationError("DISCOUNT_CODE_USAGE_LIMIT_REACHED")

    if discount_code.min_subtotal is not None and subtotal < discount_code.min_subtotal:
        raise DiscountValidationError("DISCOUNT_CODE_MIN_SUBTOTAL_NOT_MET")

    if discount_code.single_use_per_user:
        used_by_user = db.execute(
            select(DiscountCodeUsage.id).where(
                DiscountCodeUsage.tenant_id == tenant_id,
                DiscountCodeUsage.discount_code_id == discount_code.id,
                DiscountCodeUsage.used_by_user_id == user_id,
            ).limit(1)
        ).scalar_one_or_none()
        if used_by_user is not None:
            raise DiscountValidationError("DISCOUNT_CODE_ALREADY_USED_BY_USER")

    discount_amount = compute_discount_amount(
        subtotal, discount_code.discount_type, Decimal(discount_code.discount_value)
    )
    total = (subtotal - discount_amount).quantize(Decimal("0.01"))
    return discount_code, discount_amount, total


def register_discount_usage(
    db: Session,
    tenant_id: uuid.UUID,
    discount_code: DiscountCode,
    user_id: uuid.UUID,
    subtotal: Decimal,
    discount_amount: Decimal,
    total: Decimal,
    group_event_id: uuid.UUID | None,
    reservation_id: uuid.UUID | None,
) -> DiscountCodeUsage:
    usage = DiscountCodeUsage(
        tenant_id=tenant_id,
        discount_code_id=discount_code.id,
        used_by_user_id=user_id,
        applied_subtotal=subtotal,
        applied_discount_amount=discount_amount,
        applied_total=total,
        group_event_id=group_event_id,
        reservation_id=reservation_id,
    )
    discount_code.used_count = (discount_code.used_count or 0) + 1
    db.add(usage)
    db.flush()
    db.refresh(usage)
    return usage
