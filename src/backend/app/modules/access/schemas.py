"""Access API schemas."""

from pydantic import BaseModel
from uuid import UUID


class ValidateQRBody(BaseModel):
    token: str


class ValidateQRResponse(BaseModel):
    acceso: str  # AUTORIZADO | RECHAZADO
    color: str   # VERDE | ROJO
    motivo: str
    nombre_evento: str | None = None
    espacio: str | None = None
    readiness_pct: float | None = None
    pending_critical_items: list[dict] | None = None
    pending_evidence: list[dict] | None = None
