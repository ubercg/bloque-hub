"""Schemas para mensajes del portal."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PortalMessageCreate(BaseModel):
    mensaje: str = Field(..., min_length=1, max_length=10000)


class PortalMessageRead(BaseModel):
    id: UUID
    reservation_id: UUID
    remitente_tipo: str
    remitente_id: UUID
    mensaje: str
    enviado_at: datetime
    leido_at: datetime | None

    class Config:
        from_attributes = True
