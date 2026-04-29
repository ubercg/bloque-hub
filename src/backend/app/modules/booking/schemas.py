from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.booking.models import ReservationStatus


class ReservationCreate(BaseModel):
    space_id: UUID
    fecha: date
    hora_inicio: time
    hora_fin: time


class ReservationSlotCreate(BaseModel):
    space_id: UUID
    fecha: date
    hora_inicio: time
    hora_fin: time


class ReservationEventCreate(BaseModel):
    event_name: str | None = Field(None, max_length=255)
    discount_code: str | None = Field(None, min_length=3, max_length=64)
    items: list[ReservationSlotCreate] = Field(..., min_length=1)


class ReservationRead(BaseModel):
    id: UUID
    tenant_id: UUID
    user_id: UUID
    space_id: UUID
    group_event_id: UUID | None = None
    discount_code_id: UUID | None = None
    discount_amount_applied: float | None = None
    event_name: str | None = None
    fecha: date
    hora_inicio: time
    hora_fin: time
    status: ReservationStatus
    ttl_expires_at: datetime | None = None
    ttl_frozen: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReservationEventRead(BaseModel):
    group_event_id: UUID
    event_name: str | None = None
    reservations: list[ReservationRead]


class RejectBody(BaseModel):
    motivo: str | None = Field(None, max_length=500)


class BulkGenerateSlipBody(BaseModel):
    """Generate Pase de Caja for every PENDING_SLIP slot in a group. Exactly one of the fields should be set."""

    group_event_id: UUID | None = None
    reservation_ids: list[UUID] | None = None


class SlipPreviewItem(BaseModel):
    reservation_id: UUID
    html: str


class BulkSlipPreviewResponse(BaseModel):
    items: list[SlipPreviewItem]


class PaymentVoucherRead(BaseModel):
    """Payment voucher (comprobante de pago) read schema."""

    id: UUID
    reservation_id: UUID
    file_url: str
    file_type: str
    file_size_kb: int
    sha256_hash: str
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class EventSummaryBlock(BaseModel):
    start: time
    end: time
    hours: float  # JSON-friendly; viene de Decimal cuantizado
    reservation_ids: list[UUID]


class EventSummaryDay(BaseModel):
    date: date
    blocks: list[EventSummaryBlock]


class EventSummarySpace(BaseModel):
    space_id: UUID
    space_name: str
    days: list[EventSummaryDay]


class EventSummaryTotals(BaseModel):
    unique_spaces: int
    total_hours: float


class EventSummaryEvent(BaseModel):
    group_event_id: UUID | None = None
    name: str | None = None
    date_from: date
    date_to: date
    status_primary: ReservationStatus
    status_is_mixed: bool = False


class EventSummaryResponse(BaseModel):
    event: EventSummaryEvent
    totals: EventSummaryTotals
    spaces: list[EventSummarySpace]
