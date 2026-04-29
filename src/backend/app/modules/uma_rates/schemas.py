import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class UmaRateBase(BaseModel):
    value: Decimal = Field(..., gt=0, decimal_places=4)
    effective_date: date


class UmaRateCreate(UmaRateBase):
    pass


class UmaRateResponse(UmaRateBase):
    id: uuid.UUID
    tenant_id: uuid.UUID
    created_by: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
