import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PricingRuleBase(BaseModel):
    base_6h: Decimal = Field(..., ge=0, max_digits=12, decimal_places=4)
    base_12h: Decimal = Field(..., ge=0, max_digits=12, decimal_places=4)
    extra_hour_rate: Decimal = Field(..., ge=0, max_digits=12, decimal_places=4)
    discount_threshold: Decimal = Field(default=Decimal("0"), ge=0, max_digits=5, decimal_places=2)
    effective_from: date
    effective_to: date | None = None


class PricingRuleCreate(PricingRuleBase):
    space_id: uuid.UUID


class PricingRuleUpdate(BaseModel):
    base_6h: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=4)
    base_12h: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=4)
    extra_hour_rate: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=4)
    discount_threshold: Decimal | None = Field(None, ge=0, max_digits=5, decimal_places=2)
    effective_from: date | None = None
    effective_to: date | None = None


class PricingRuleResponse(PricingRuleBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    space_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class QuoteCalculationRequest(BaseModel):
    space_id: uuid.UUID
    target_date: date
    duration_hours: Decimal


class QuoteCalculationResponse(BaseModel):
    space_id: uuid.UUID
    target_date: date
    duration_hours: Decimal
    base_price: Decimal
    total_price: Decimal
