"""Pydantic schemas for CRM (Lead, Quote, QuoteItem)."""

from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.crm.models import ContractStatus, QuoteStatus


# ----- Lead -----


class LeadCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., max_length=255)
    phone: str | None = Field(None, max_length=64)
    company: str | None = Field(None, max_length=255)
    notes: str | None = None


class LeadRead(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    email: str
    phone: str | None
    company: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LeadUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    email: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=64)
    company: str | None = Field(None, max_length=255)
    notes: str | None = None


# ----- QuoteItem -----


class QuoteItemCreate(BaseModel):
    space_id: UUID
    fecha: date
    hora_inicio: time
    hora_fin: time
    precio: float = Field(..., ge=0)
    item_order: int = Field(default=0, ge=0)
    discount_pct: float | None = None
    discount_amount: float | None = None
    discount_justification: str | None = None
    frozen_price: float | None = None


class QuoteItemRead(BaseModel):
    id: UUID
    quote_id: UUID
    space_id: UUID
    fecha: date
    hora_inicio: time
    hora_fin: time
    precio: float
    item_order: int
    discount_pct: float | None = None
    discount_amount: float | None = None
    discount_justification: str | None = None
    frozen_price: float | None = None

    model_config = {"from_attributes": True}


# ----- Quote -----


class QuoteCreate(BaseModel):
    lead_id: UUID
    items: list[QuoteItemCreate] = Field(..., min_length=1)
    discount_pct: float | None = None
    discount_amount: float | None = None
    discount_justification: str | None = None


class QuoteRead(BaseModel):
    id: UUID
    tenant_id: UUID
    lead_id: UUID
    status: QuoteStatus
    total: float
    soft_hold_expires_at: datetime | None
    uma_snapshot_value: float | None = None
    uma_snapshot_reference: str | None = None
    discount_pct: float | None = None
    discount_amount: float | None = None
    discount_justification: str | None = None
    created_at: datetime
    updated_at: datetime
    items: list[QuoteItemRead] = []

    model_config = {"from_attributes": True}


class QuoteStatusUpdate(BaseModel):
    status: QuoteStatus


# ----- Contract -----


class ContractRead(BaseModel):
    id: UUID
    tenant_id: UUID
    quote_id: UUID
    status: ContractStatus
    provider_document_id: str | None
    signed_document_url: str | None
    fea_provider: str | None
    sent_at: datetime | None
    delegate_signer_activated_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
