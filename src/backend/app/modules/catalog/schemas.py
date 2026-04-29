from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from uuid import UUID
from .models import UnitType

class AdditionalServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    unit_type: UnitType
    uma_factor: Optional[float] = None
    base_price: Optional[float] = None
    is_active: bool = True

class AdditionalServiceCreate(AdditionalServiceBase):
    pass

class AdditionalServiceResponse(AdditionalServiceBase):
    id: UUID
    tenant_id: UUID

    model_config = ConfigDict(from_attributes=True)