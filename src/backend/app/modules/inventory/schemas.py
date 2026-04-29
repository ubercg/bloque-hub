import enum
from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.inventory.models import BookingMode, RelationshipType, SlotStatus


# ----- Space -----


class SpacePromoMediaUploadResponse(BaseModel):
    """URL pública (misma origin vía nginx) para usar en promo_hero_url o promo_gallery_urls."""

    url: str


class SpaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=64)
    booking_mode: BookingMode = BookingMode.QUOTE_REQUIRED
    capacidad_maxima: int = Field(..., ge=0)
    layouts: dict | None = None
    precio_por_hora: float = Field(..., ge=0)
    ttl_minutos: int = Field(default=1440, ge=1)
    is_active: bool = True
    piso: int | None = Field(None, ge=0, le=7)
    descripcion: str | None = None
    matterport_url: str | None = None
    promo_hero_url: str | None = None
    promo_gallery_urls: list[str] | None = None
    amenidades: list[str] | None = None


class SpaceRead(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    slug: str
    booking_mode: BookingMode
    capacidad_maxima: int
    layouts: dict | None
    precio_por_hora: float
    ttl_minutos: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    piso: int | None = None
    descripcion: str | None = None
    matterport_url: str | None = None
    promo_hero_url: str | None = None
    promo_gallery_urls: list[str] | None = None
    amenidades: list[str] | None = None

    model_config = {"from_attributes": True}


class SpaceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    slug: str | None = Field(None, min_length=1, max_length=64)
    booking_mode: BookingMode | None = None
    capacidad_maxima: int | None = Field(None, ge=0)
    layouts: dict | None = None
    precio_por_hora: float | None = Field(None, ge=0)
    ttl_minutos: int | None = Field(None, ge=1)
    is_active: bool | None = None
    piso: int | None = Field(None, ge=0, le=7)
    descripcion: str | None = None
    matterport_url: str | None = None
    promo_hero_url: str | None = None
    promo_gallery_urls: list[str] | None = None
    amenidades: list[str] | None = None


# ----- SpaceRelationship -----


class SpaceRelationshipCreate(BaseModel):
    parent_space_id: UUID
    child_space_id: UUID
    relationship_type: RelationshipType = RelationshipType.PARENT_CHILD


class SpaceRelationshipRead(BaseModel):
    id: UUID
    tenant_id: UUID
    parent_space_id: UUID
    child_space_id: UUID
    relationship_type: RelationshipType
    created_at: datetime

    model_config = {"from_attributes": True}


# ----- Inventory / Slot -----


class SlotRead(BaseModel):
    id: UUID
    space_id: UUID
    tenant_id: UUID
    fecha: date
    hora_inicio: time
    hora_fin: time
    estado: SlotStatus
    reservation_id: UUID | None
    quote_id: UUID | None
    ttl_frozen: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OccupancyStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    TENTATIVE = "TENTATIVE"
    CONFIRMED = "CONFIRMED"


class OccupancySlotRead(BaseModel):
    slot_id: UUID
    fecha: date
    hora_inicio: time
    hora_fin: time
    duracion_horas: float

    space_id: UUID
    space_name: str
    slot_status: SlotStatus
    occupancy_status: OccupancyStatus

    reservation_id: UUID | None = None
    group_event_id: UUID | None = None
    event_name: str | None = None
    reservation_status: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    related_space_name: str | None = None
    related_event_name: str | None = None
    related_customer_name: str | None = None


class AvailabilityQuery(BaseModel):
    space_id: UUID
    fecha_desde: date
    fecha_hasta: date


class BlockSlotRequest(BaseModel):
    fecha: date
    hora_inicio: time
    hora_fin: time
    as_parent: bool = False  # True: block parent and children; False: block child and parent


# ----- Space Booking Rules -----


class SpaceBookingRuleUpsert(BaseModel):
    min_duration_minutes: int = Field(..., ge=1)
    allowed_start_times: list[str] = Field(..., min_length=1)


class SpaceBookingRuleRead(BaseModel):
    id: UUID
    space_id: UUID
    tenant_id: UUID
    min_duration_minutes: int
    allowed_start_times: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ----- Availability Calendar (FR-03) -----


class CalendarDaySlot(BaseModel):
    """Public-facing slot for calendar view. Status mapped for frontend colors."""
    fecha: date
    hora_inicio: time
    hora_fin: time
    status: str  # AVAILABLE | BLOCKED | TTL_PENDING


class MonthAvailabilityResponse(BaseModel):
    month: str
    days: dict[str, list[CalendarDaySlot]]


# ----- Check Availability (FR-03) -----


class CheckAvailabilityRequest(BaseModel):
    espacio_id: UUID
    fecha: date
    hora_inicio: time
    hora_fin: time


class CheckAvailabilityResponse(BaseModel):
    available: bool
    estado: str
    motivo: str
    allowed_blocks: list[str] | None = None


class CheckAvailabilityGroupRequest(BaseModel):
    items: list[CheckAvailabilityRequest] = Field(..., min_length=1)


class ConflictItem(BaseModel):
    espacio_id: UUID
    estado: str
    motivo: str


class CheckAvailabilityGroupResponse(BaseModel):
    all_available: bool
    conflicts: list[ConflictItem]
