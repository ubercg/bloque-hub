"""CRM models: Lead, Quote, QuoteItem."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, time
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
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


# Registrar AdditionalService en el mismo metadata que CRM (evita error de mapper).
from app.modules.catalog.models import AdditionalService  # noqa: E402, F401
