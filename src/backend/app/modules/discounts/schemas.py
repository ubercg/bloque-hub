from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


DiscountType = Literal["PERCENT", "FIXED"]


class DiscountCodeCreate(BaseModel):
    code: str = Field(..., min_length=3, max_length=64)
    discount_type: DiscountType
    discount_value: Decimal = Field(..., gt=0, decimal_places=4)
    min_subtotal: Decimal | None = Field(None, ge=0, decimal_places=4)
    max_uses: int | None = Field(None, ge=1)
    active: bool = True
    expires_at: datetime | None = None
    single_use_per_user: bool = False
    description: str | None = Field(None, max_length=1000)


class DiscountCodeUpdate(BaseModel):
    discount_value: Decimal | None = Field(None, gt=0, decimal_places=4)
    min_subtotal: Decimal | None = Field(None, ge=0, decimal_places=4)
    max_uses: int | None = Field(None, ge=1)
    active: bool | None = None
    expires_at: datetime | None = None
    single_use_per_user: bool | None = None
    description: str | None = Field(None, max_length=1000)


class DiscountCodeRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    code: str
    discount_type: DiscountType
    discount_value: Decimal
    min_subtotal: Decimal | None
    max_uses: int | None
    used_count: int
    active: bool
    expires_at: datetime | None
    single_use_per_user: bool
    description: str | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    status: str

    model_config = {"from_attributes": True}


class DiscountCodeUsageRead(BaseModel):
    id: uuid.UUID
    discount_code_id: uuid.UUID
    group_event_id: uuid.UUID | None
    reservation_id: uuid.UUID | None
    used_by_user_id: uuid.UUID
    applied_subtotal: Decimal
    applied_discount_amount: Decimal
    applied_total: Decimal
    used_at: datetime

    model_config = {"from_attributes": True}


class DiscountValidateRequest(BaseModel):
    code: str = Field(..., min_length=3, max_length=64)
    subtotal: Decimal = Field(..., ge=0, decimal_places=4)


class DiscountValidateResponse(BaseModel):
    valid: bool
    code: str
    discount_code_id: uuid.UUID | None = None
    discount_type: DiscountType | None = None
    discount_value: Decimal | None = None
    discount_amount: Decimal = Decimal("0")
    subtotal: Decimal
    total: Decimal
    reason: str | None = None
