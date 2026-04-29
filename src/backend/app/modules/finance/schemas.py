"""Pydantic schemas for CFDI and credit balances."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CfdiDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reservation_id: uuid.UUID
    tipo: str
    uuid_fiscal: uuid.UUID | None
    estado: str
    monto: float
    timbrado_at: datetime | None
    error_codigo: str | None
    error_descripcion: str | None
    pdf_url: str | None = None
    xml_url: str | None = None


class CreditBalanceRead(BaseModel):
    """Saldo a favor (nota de crédito) para listado en Finanzas."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    cfdi_uuid: uuid.UUID
    monto_original: float
    saldo_restante: float
    reservation_origen_id: uuid.UUID | None
    aplicado_a_reservation_id: uuid.UUID | None
    created_at: datetime


class CreditApplyBody(BaseModel):
    """Body para aplicar un crédito a una reserva."""

    reservation_id: uuid.UUID
    monto_a_aplicar: float = Field(..., gt=0, description="Monto a aplicar (máximo saldo_restante)")
