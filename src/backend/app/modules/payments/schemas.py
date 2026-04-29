import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class PaymentReferenceCreate(BaseModel):
    reservation_id: uuid.UUID
    amount: float = Field(gt=0)

class PaymentReferenceResponse(BaseModel):
    id: uuid.UUID
    reservation_id: uuid.UUID
    reference_code: str
    amount: float
    status: str
    created_at: datetime
    paid_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

class SPEIWebhookPayload(BaseModel):
    reference_code: str
    amount_paid: float
    payment_date: datetime
    tracking_key: str