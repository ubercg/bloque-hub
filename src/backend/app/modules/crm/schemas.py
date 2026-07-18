"""Pydantic schemas for CRM (Lead, Quote, QuoteItem)."""

from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.modules.crm.models import (
    CaracterEvento,
    ComoConociste,
    ContractStatus,
    MontajeRequerido,
    QuoteStatus,
    Sector,
    ServicioApoyo,
    TipoEvento,
)
from app.modules.portal_gate.client import is_valid_folio_format


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


# ----- Public quote-request wizard (REQ-012) -----
# Server-side validation is the source of truth for RN-005..RN-011, RN-014, RN-017
# (design.md §2.3). These DTOs are independent of any client-side UI state.


class PublicWizardItem(BaseModel):
    """Step 2 item. No client-supplied `precio` — the server always computes it."""

    space_id: UUID
    fecha: date
    hora_inicio: time
    hora_fin: time


class PublicQuoteRequestCreate(BaseModel):
    folio: str

    # Step 1: Evento
    tipo_evento: TipoEvento
    nombre_evento: str | None = None
    caracter_evento: CaracterEvento
    descripcion_evento: str | None = None
    asistentes_estimados: int = Field(..., gt=0)  # RN-007
    habra_prensa: bool

    # Step 2: Espacio/fecha (multi-item, RN-012)
    items: list[PublicWizardItem] = Field(..., min_length=1)

    # Step 3: Solicitante
    nombre_completo: str = Field(..., min_length=1)
    cargo_puesto: str | None = None
    institucion_organizacion: str | None = None
    sector: Sector
    sector_otro: str | None = None
    correo_institucional: EmailStr
    telefono_contacto: str = Field(..., min_length=1)
    responsable_sitio_nombre: str | None = None
    responsable_sitio_telefono: str | None = None
    como_conociste_bloque: ComoConociste
    como_conociste_otro: str | None = None

    # Step 4: Servicios y montaje
    # FIXED closed enum (REQ-012 §4.5), NOT a catalog lookup — optional, not priced.
    servicios_apoyo: list[ServicioApoyo] = []
    montaje_requerido: MontajeRequerido
    requerimientos_especiales: str | None = None
    material_externo: bool = False
    material_externo_detalle: str | None = None

    # Step 5: Legal acceptances (RN-014)
    acepta_info_correcta_autorizacion: bool
    acepta_reglamento_y_aviso_privacidad: bool

    @field_validator("folio")
    @classmethod
    def _folio_format(cls, v: str) -> str:
        # RN-017 — reuse the same regex used by the gate/revalidation client so
        # the format rule is defined in exactly one place.
        if not is_valid_folio_format(v):
            raise ValueError(
                "folio debe cumplir el formato BCE-YYYYMMDD-HHMMSS-RRRR"
            )
        return v

    @model_validator(mode="after")
    def _conditionals(self) -> "PublicQuoteRequestCreate":
        if self.tipo_evento == TipoEvento.OTRO and not (
            self.nombre_evento or ""
        ).strip():
            raise ValueError(
                "nombre_evento requerido cuando tipo_evento=Otro"
            )  # RN-008
        if self.sector == Sector.OTRO and not (self.sector_otro or "").strip():
            raise ValueError("sector_otro requerido cuando sector=Otro")  # RN-009
        if self.como_conociste_bloque == ComoConociste.OTRO and not (
            self.como_conociste_otro or ""
        ).strip():
            raise ValueError(
                "como_conociste_otro requerido cuando como_conociste_bloque=Otro"
            )  # RN-010
        if self.material_externo and not (
            self.material_externo_detalle or ""
        ).strip():
            raise ValueError(
                "material_externo_detalle requerido cuando material_externo=true"
            )  # RN-011
        if self.descripcion_evento and len(self.descripcion_evento.split()) > 300:
            raise ValueError("descripcion_evento excede 300 palabras")  # RN-006
        if not (
            self.acepta_info_correcta_autorizacion
            and self.acepta_reglamento_y_aviso_privacidad
        ):
            raise ValueError(
                "Ambas aceptaciones legales son requeridas"
            )  # RN-014
        return self
