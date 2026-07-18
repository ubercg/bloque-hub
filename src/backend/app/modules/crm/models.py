"""CRM models: Lead, Quote, QuoteItem."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, time
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.modules.catalog.models import AdditionalService

# Forward ref for Space (inventory) - use string in relationship to avoid circular import


class QuoteStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    DRAFT_PENDING_OPS = "DRAFT_PENDING_OPS"
    SENT = "SENT"
    APPROVED = "APPROVED"
    DIGITAL_APPROVED = "DIGITAL_APPROVED"


class ContractStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    SIGNED = "signed"
    REJECTED = "rejected"
    EXPIRED = "expired"


class DiscountRequestStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ServiceUnit(str, enum.Enum):
    MINUTO = "MINUTO"
    EVENTO = "EVENTO"
    M2 = "M2"


# --- Public quote-request wizard enums (REQ-012). Values FROZEN from REQ-012 §4 —
# do NOT invent/change; enum values are costly to migrate post-release. ---


class TipoEvento(str, enum.Enum):
    FIRMA_CONVENIO = "Firma de convenio"
    CONFERENCIA = "Conferencia"
    TALLER = "Taller / Workshop"
    PRESENTACION = "Presentación"
    NETWORKING = "Networking"
    RUEDA_PRENSA = "Rueda de prensa"
    REUNION_INSTITUCIONAL = "Reunión institucional"
    OTRO = "Otro"


class CaracterEvento(str, enum.Enum):
    PUBLICO = "Público"
    PRIVADO = "Privado"
    GUBERNAMENTAL = "Gubernamental"
    ACADEMICO = "Académico"
    EMPRESARIAL = "Empresarial"


class Sector(str, enum.Enum):
    GOBIERNO_MUNICIPAL_ESTATAL_FEDERAL = "Gobierno municipal/estatal/federal"
    UNIVERSIDAD_INSTITUCION_EDUCATIVA = "Universidad / Institución educativa"
    EMPRESA_PRIVADA = "Empresa privada"
    ORGANISMO_INTERNACIONAL = "Organismo internacional"
    ORGANIZACION_CIVIL = "Organización civil"
    STARTUP_EMPRENDIMIENTO = "Startup / Emprendimiento"
    OTRO = "Otro"


class ComoConociste(str, enum.Enum):
    RECOMENDACION_OTRA_INSTITUCION = "Recomendación de otra institución"
    REDES_SOCIALES = "Redes sociales"
    SITIO_WEB_MUNICIPIO = "Sitio web del Municipio"
    YA_REALIZADO_EVENTOS_ANTERIORES = "Ya he realizado eventos anteriores"
    OTRO = "Otro"


class MontajeRequerido(str, enum.Enum):
    ESTANDAR_MESAS_SILLAS_U = "Estándar (mesas y sillas en U)"
    TEATRO = "Teatro"
    AULA = "Aula"
    COCTEL = "Cóctel"
    PROTOCOLAR_FIRMA = "Protocolar para firma"
    SIN_MONTAJE = "Sin montaje"


class ServicioApoyo(str, enum.Enum):
    """Step 4 `servicios_apoyo` — FIXED closed multi-enum (REQ-012 §4.5), NOT a
    dynamic catalog. Not priced (Quote.total = spaces only, PR#8 correction —
    see design.md deviation note)."""

    EQUIPO_AUDIOVISUAL = "Equipo audiovisual"
    FOTOGRAFIA_OFICIAL = "Fotografía oficial"
    TRANSMISION_EN_VIVO = "Transmisión en vivo"
    COFFEE_BREAK = "Coffee break"
    REGISTRO_DE_ASISTENTES = "Registro de asistentes"
    TRADUCCION_SIMULTANEA = "Traducción simultánea"
    ESTACIONAMIENTO_VIP = "Estacionamiento VIP"
    DIFUSION_REDES_BLOQUE = "Difusión en redes de BLOQUE"


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    quotes: Mapped[list["Quote"]] = relationship(
        "Quote", back_populates="lead", cascade="all, delete-orphan"
    )


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[QuoteStatus] = mapped_column(
        Enum(QuoteStatus), nullable=False, default=QuoteStatus.DRAFT
    )
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    soft_hold_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    uma_snapshot_value: Mapped[float | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    uma_snapshot_reference: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    discount_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    discount_amount: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    discount_justification: Mapped[str | None] = mapped_column(Text, nullable=True)

    # REQ-012: public quote-request wizard. NULL for internal COMMERCIAL quotes
    # (created via create_quote); set for wizard-originated quotes. Uniqueness is
    # enforced by a partial unique index (WHERE portal_folio IS NOT NULL) created
    # in the migration, not by a column-level constraint, so multiple NULLs coexist.
    portal_folio: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )

    lead: Mapped["Lead"] = relationship("Lead", back_populates="quotes")
    items: Mapped[list["QuoteItem"]] = relationship(
        "QuoteItem",
        back_populates="quote",
        cascade="all, delete-orphan",
        order_by="QuoteItem.item_order",
    )
    additional_services: Mapped[list["QuoteAdditionalService"]] = relationship(
        "QuoteAdditionalService", back_populates="quote", cascade="all, delete-orphan"
    )
    contract: Mapped["Contract | None"] = relationship(
        "Contract", back_populates="quote", uselist=False, cascade="all, delete-orphan"
    )
    wizard_details: Mapped["QuoteWizardDetails | None"] = relationship(
        "QuoteWizardDetails",
        back_populates="quote",
        uselist=False,
        cascade="all, delete-orphan",
    )
    wizard_documents: Mapped[list["QuoteWizardDocuments"]] = relationship(
        "QuoteWizardDocuments", back_populates="quote", cascade="all, delete-orphan"
    )


class QuoteItem(Base):
    __tablename__ = "quote_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False
    )
    space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    hora_inicio: Mapped[time] = mapped_column(Time, nullable=False)
    hora_fin: Mapped[time] = mapped_column(Time, nullable=False)
    precio: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    item_order: Mapped[int] = mapped_column(default=0, nullable=False)

    uma_snapshot: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    uma_snapshot_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    discount_amount: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    discount_percentage: Mapped[float | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    subtotal_frozen: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)

    quote: Mapped["Quote"] = relationship("Quote", back_populates="items")
    space: Mapped["Space"] = relationship(  # type: ignore[name-defined]
        "Space", foreign_keys=[space_id]
    )
    discount_requests: Mapped[list["DiscountRequest"]] = relationship(
        "DiscountRequest", back_populates="quote_item", cascade="all, delete-orphan"
    )


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status: Mapped[ContractStatus] = mapped_column(
        Enum(ContractStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ContractStatus.PENDING,
    )
    provider_document_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    signed_document_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    fea_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    contract_snapshot_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    delegate_signer_activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    quote: Mapped["Quote"] = relationship("Quote", back_populates="contract")


class QuoteAdditionalService(Base):
    __tablename__ = "quote_additional_services"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("additional_services.id", ondelete="CASCADE"),
        nullable=False,
    )
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    calculated_price: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)

    quote: Mapped["Quote"] = relationship("Quote", back_populates="additional_services")
    service: Mapped["AdditionalService"] = relationship(
        "AdditionalService",
        foreign_keys=[service_id],
    )


class DiscountRequest(Base):
    __tablename__ = "discount_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    quote_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quote_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    percentage: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[DiscountRequestStatus] = mapped_column(
        Enum(DiscountRequestStatus),
        nullable=False,
        default=DiscountRequestStatus.PENDING,
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    quote_item: Mapped["QuoteItem"] = relationship(
        "QuoteItem", back_populates="discount_requests"
    )


class QuoteWizardDetails(Base):
    """1:1 adjunct to Quote holding public wizard-only fields (REQ-012).

    Kept separate from `quotes`/`leads` so the internal COMMERCIAL flow does not
    grow wizard-only columns (design.md §1.3, ADR-3).
    """

    __tablename__ = "quote_wizard_details"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # enforces 1:1
    )

    # --- Step 1: Evento ---
    tipo_evento: Mapped[TipoEvento] = mapped_column(
        Enum(TipoEvento, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    nombre_evento: Mapped[str | None] = mapped_column(String(255), nullable=True)
    caracter_evento: Mapped[CaracterEvento] = mapped_column(
        Enum(CaracterEvento, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    descripcion_evento: Mapped[str | None] = mapped_column(Text, nullable=True)
    asistentes_estimados: Mapped[int] = mapped_column(Integer, nullable=False)
    habra_prensa: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # --- Step 3: Solicitante ---
    nombre_completo: Mapped[str] = mapped_column(String(255), nullable=False)
    cargo_puesto: Mapped[str | None] = mapped_column(String(255), nullable=True)
    institucion_organizacion: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    sector: Mapped[Sector] = mapped_column(
        Enum(Sector, values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    sector_otro: Mapped[str | None] = mapped_column(String(255), nullable=True)
    correo_institucional: Mapped[str] = mapped_column(String(255), nullable=False)
    telefono_contacto: Mapped[str] = mapped_column(String(64), nullable=False)
    responsable_sitio_nombre: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    responsable_sitio_telefono: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    como_conociste_bloque: Mapped[ComoConociste] = mapped_column(
        Enum(ComoConociste, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    como_conociste_otro: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- Step 4: Servicios y montaje ---
    # servicios_apoyo: fixed enum values stored as text[], NOT a catalog FK
    # (REQ-012 §4.5 — PR#8 correction). Optional; not priced.
    servicios_apoyo: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), nullable=False, default=list, server_default="{}"
    )
    montaje_requerido: Mapped[MontajeRequerido] = mapped_column(
        Enum(MontajeRequerido, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    requerimientos_especiales: Mapped[str | None] = mapped_column(Text, nullable=True)
    material_externo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    material_externo_detalle: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Step 5: Legal acceptances (RN-014) ---
    acepta_info_correcta_autorizacion: Mapped[bool] = mapped_column(
        Boolean, nullable=False
    )
    acepta_reglamento_y_aviso_privacidad: Mapped[bool] = mapped_column(
        Boolean, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    quote: Mapped["Quote"] = relationship(
        "Quote", back_populates="wizard_details", uselist=False
    )


class QuoteWizardDocuments(Base):
    """1:N documents attached to a public wizard quote request (REQ-012, RN-015).

    Option B from design.md §1.4: documents are persisted relationally, keyed by
    quote_id (there is no reservation in the wizard flow).
    """

    __tablename__ = "quote_wizard_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False
    )
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    quote: Mapped["Quote"] = relationship("Quote", back_populates="wizard_documents")


# Registrar AdditionalService en el mismo metadata que CRM (evita error de mapper).
from app.modules.catalog.models import AdditionalService  # noqa: E402, F401
