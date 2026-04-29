"""Fulfillment models: MasterServiceOrder, Checklist, ServiceOrderItem."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MasterServiceOrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    READY = "READY"
    CANCELLED = "CANCELLED"


class ServiceOrderItemStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"


class EvidenceStatus(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    PENDIENTE_REVISION = "PENDIENTE_REVISION"
    APROBADO = "APROBADO"
    RECHAZADO = "RECHAZADO"


class MasterServiceOrder(Base):
    __tablename__ = "master_service_orders"
    __table_args__ = (
        CheckConstraint(
            "reservation_id IS NOT NULL OR contract_id IS NOT NULL",
            name="chk_os_reservation_or_contract",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reservations.id", ondelete="CASCADE"),
        nullable=True,
    )
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=True,
    )
    status: Mapped[MasterServiceOrderStatus] = mapped_column(
        Enum(MasterServiceOrderStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=MasterServiceOrderStatus.PENDING,
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

    reservation: Mapped["Reservation | None"] = relationship(  # noqa: F821
        "Reservation", foreign_keys=[reservation_id]
    )
    contract: Mapped["Contract | None"] = relationship(  # noqa: F821
        "Contract", foreign_keys=[contract_id]
    )
    checklists: Mapped[list["Checklist"]] = relationship(
        "Checklist",
        back_populates="master_service_order",
        cascade="all, delete-orphan",
        order_by="Checklist.item_order",
    )
    evidence_requirements: Mapped[list["EvidenceRequirement"]] = relationship(
        "EvidenceRequirement",
        back_populates="master_service_order",
        cascade="all, delete-orphan",
    )


class Checklist(Base):
    __tablename__ = "checklists"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    master_service_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("master_service_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    item_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    master_service_order: Mapped["MasterServiceOrder"] = relationship(
        "MasterServiceOrder", back_populates="checklists"
    )
    items: Mapped[list["ServiceOrderItem"]] = relationship(
        "ServiceOrderItem",
        back_populates="checklist",
        cascade="all, delete-orphan",
        order_by="ServiceOrderItem.item_order",
    )


class ServiceOrderItem(Base):
    __tablename__ = "service_order_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    checklist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("checklists.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    item_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_critical: Mapped[bool] = mapped_column(nullable=False, default=False)
    status: Mapped[ServiceOrderItemStatus] = mapped_column(
        Enum(ServiceOrderItemStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ServiceOrderItemStatus.PENDING,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    checklist: Mapped["Checklist"] = relationship("Checklist", back_populates="items")


class EvidenceRequirement(Base):
    __tablename__ = "evidence_requirements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    master_service_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("master_service_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    tipo_documento: Mapped[str] = mapped_column(String(80), nullable=False)
    estado: Mapped[EvidenceStatus] = mapped_column(
        Enum(EvidenceStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=EvidenceStatus.PENDIENTE,
    )
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sha256_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    plazo_vence_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    uploaded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revisado_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    motivo_rechazo: Mapped[str | None] = mapped_column(Text, nullable=True)
    intentos_carga: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    master_service_order: Mapped["MasterServiceOrder"] = relationship(
        "MasterServiceOrder", back_populates="evidence_requirements"
    )


class ServiceOrderType(str, enum.Enum):
    RIDER = "RIDER"
    AUDIO = "AUDIO"
    VIDEO = "VIDEO"
    GENERAL = "GENERAL"


class ServiceOrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    READY = "READY"
    CANCELLED = "CANCELLED"


class ServiceOrder(Base):
    __tablename__ = "service_orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    reservation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reservations.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[ServiceOrderType] = mapped_column(
        Enum(ServiceOrderType), nullable=False, default=ServiceOrderType.GENERAL
    )
    status: Mapped[ServiceOrderStatus] = mapped_column(
        Enum(ServiceOrderStatus), nullable=False, default=ServiceOrderStatus.PENDING
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
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

    reservation: Mapped["Reservation"] = relationship(
        "Reservation", foreign_keys=[reservation_id]
    )
    checklist_items: Mapped[list["ChecklistItem"]] = relationship(
        "ChecklistItem", back_populates="service_order", cascade="all, delete-orphan"
    )


class ChecklistItem(Base):
    __tablename__ = "checklist_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    service_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    service_order: Mapped["ServiceOrder"] = relationship(
        "ServiceOrder", back_populates="checklist_items"
    )
