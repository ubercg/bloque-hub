"""Pydantic schemas for operations dashboard API."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.booking.models import ReservationStatus


class TimeBlockRead(BaseModel):
    """Merged contiguous block for one space and date."""

    date: date
    start: str = Field(..., description="HH:MM")
    end: str = Field(..., description="HH:MM")
    hours: float
    reservation_ids: list[UUID] = Field(default_factory=list)


class SpaceBlocksRead(BaseModel):
    space_id: UUID
    name: str
    blocks: list[TimeBlockRead]


class ReadinessFlags(BaseModel):
    documents: bool
    payment: bool
    validation: bool | None = Field(
        None,
        description="Service order readiness; null if no OS linked to any slot in the group",
    )


class ReservationGroupSummary(BaseModel):
    """One operational row: event group or single-slot reservation."""

    operational_group_id: str = Field(
        ...,
        description="group_event_id as string, or reservation.id for single-slot groups",
    )
    group_event_id: UUID | None = None
    reservation_ids: list[UUID]
    event_name: str | None = None
    date_from: date
    date_to: date
    status: ReservationStatus
    status_is_mixed: bool = False
    spaces: list[SpaceBlocksRead]
    readiness: ReadinessFlags


class OperationsKpis(BaseModel):
    events_today: int = Field(..., description="Distinct operational groups with activity on calendar today (MX)")
    spaces_occupied_today: int = Field(
        ...,
        description="Distinct spaces with a non-cancelled reservation on today (MX)",
    )
    pending_slip_groups_today: int
    confirmed_groups_today: int


class ReservationsSummaryResponse(BaseModel):
    kpis: OperationsKpis
    reservations: list[ReservationGroupSummary]
