import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.pricing.models import PricingRule
from app.modules.pricing.schemas import PricingRuleCreate, PricingRuleUpdate


class NoPricingRuleError(Exception):
    pass


class PriceBreakdown:
    def __init__(
        self,
        base_price: Decimal,
        duration_hours: Decimal,
        extra_price: Decimal,
        total_price: Decimal,
    ):
        self.base_price = base_price
        self.duration_hours = duration_hours
        self.extra_price = extra_price
        self.total_price = total_price


def calculate_hybrid_price(
    start: datetime, end: datetime, rule: PricingRule
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    duration_secs = (end - start).total_seconds()
    total_hours = Decimal(str(duration_secs / 3600.0)).quantize(Decimal("0.01"))

    if total_hours <= 6:
        base_price = rule.base_6h
        extra_price = Decimal("0.0000")
    elif total_hours <= 12:
        base_price = rule.base_12h
        extra_price = Decimal("0.0000")
    else:
        base_price = rule.base_12h
        extra_hours = total_hours - 12
        extra_price = (extra_hours * rule.extra_hour_rate).quantize(Decimal("0.0000"))

    total_price = base_price + extra_price
    return total_hours, base_price, extra_price, total_price


def create_pricing_rule(
    db: Session, tenant_id: uuid.UUID, rule: PricingRuleCreate
) -> PricingRule:
    db_rule = PricingRule(
        tenant_id=tenant_id,
        space_id=rule.space_id,
        base_6h=rule.base_6h,
        base_12h=rule.base_12h,
        extra_hour_rate=rule.extra_hour_rate,
        discount_threshold=rule.discount_threshold,
        effective_from=rule.effective_from,
        effective_to=rule.effective_to,
    )
    db.add(db_rule)
    db.flush()
    db.refresh(db_rule)
    return db_rule


def update_pricing_rule(
    db: Session, tenant_id: uuid.UUID, space_id: uuid.UUID, rule: PricingRuleUpdate
) -> PricingRule | None:
    stmt = (
        select(PricingRule)
        .where(
            PricingRule.space_id == space_id,
            PricingRule.tenant_id == tenant_id,
        )
        .order_by(PricingRule.effective_from.desc(), PricingRule.created_at.desc())
    )
    db_rule = db.execute(stmt).scalars().first()
    if not db_rule:
        return None
    for k, v in rule.model_dump(exclude_unset=True).items():
        setattr(db_rule, k, v)
    db.flush()
    db.refresh(db_rule)
    return db_rule


def get_pricing_rule_by_space(
    db: Session,
    tenant_id: uuid.UUID,
    space_id: uuid.UUID,
    target_date: date | None = None,
) -> PricingRule | None:
    stmt = select(PricingRule).where(
        PricingRule.space_id == space_id,
        PricingRule.tenant_id == tenant_id,
    )
    if target_date is not None:
        stmt = stmt.where(
            PricingRule.effective_from <= target_date,
            (PricingRule.effective_to.is_(None))
            | (PricingRule.effective_to >= target_date),
        )
    stmt = stmt.order_by(
        PricingRule.effective_from.desc(), PricingRule.created_at.desc()
    )
    return db.execute(stmt).scalars().first()


def calculate_price(
    space_id: uuid.UUID,
    duration_hours: Decimal,
    tenant_id: uuid.UUID,
    target_date: date,
    db: Session,
) -> PriceBreakdown:
    if duration_hours <= 0:
        raise ValueError("Duration hours must be > 0")

    rule = get_pricing_rule_by_space(db, tenant_id, space_id, target_date)
    if not rule:
        raise NoPricingRuleError(
            f"No pricing rule for space {space_id} on {target_date}"
        )

    start = datetime(2000, 1, 1, 0, 0)
    import datetime as dt

    end = start + dt.timedelta(hours=float(duration_hours))
    h, b, e, t = calculate_hybrid_price(start, end, rule)

    return PriceBreakdown(
        base_price=b, duration_hours=h, extra_price=e, total_price=t
    )


def get_quote_for_space(
    db: Session,
    tenant_id: uuid.UUID,
    space_id: uuid.UUID,
    target_date: date,
    duration_hours: Decimal,
) -> dict:
    breakdown = calculate_price(
        space_id, duration_hours, tenant_id, target_date, db
    )
    return {
        "space_id": space_id,
        "target_date": target_date,
        "total_hours": breakdown.duration_hours,
        "base_price": breakdown.base_price,
        "extra_hours_price": breakdown.extra_price,
        "total_price": breakdown.total_price,
    }
