import enum
import uuid
from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, Time, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class BookingMode(str, enum.Enum):
    SEMI_DIRECT = "SEMI_DIRECT"
    QUOTE_REQUIRED = "QUOTE_REQUIRED"


class RelationshipType(str, enum.Enum):
    PARENT_CHILD = "PARENT_CHILD"


class SlotStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    BLOCKED_BY_PARENT = "BLOCKED_BY_PARENT"
    BLOCKED_BY_CHILD = "BLOCKED_BY_CHILD"
    TTL_BLOCKED = "TTL_BLOCKED"
    RESERVED = "RESERVED"
    SOFT_HOLD = "SOFT_HOLD"
    MAINTENANCE = "MAINTENANCE"


class Space(Base):
    __tablename__ = "spaces"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_spaces_tenant_slug"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    booking_mode: Mapped[BookingMode] = mapped_column(
        Enum(BookingMode), nullable=False, default=BookingMode.QUOTE_REQUIRED
    )
    capacidad_maxima: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    layouts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    precio_por_hora: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    ttl_minutos: Mapped[int] = mapped_column(Integer, nullable=False, default=1440)  # 24h
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Catalog / frontend (El Elevador, fichas)
    piso: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0-7 floor for filter
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    matterport_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # Rutas URL o públicas (/media/...) para hero y galería (PNG/JPG) en catálogo promocional
    promo_hero_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    promo_gallery_urls: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    amenidades: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)  # ["WiFi", "Proyector", ...]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships: as parent and as child (via SpaceRelationship)
    children_rel: Mapped[list["SpaceRelationship"]] = relationship(
        "SpaceRelationship",
        foreign_keys="SpaceRelationship.parent_space_id",
        back_populates="parent_space",
    )
    parents_rel: Mapped[list["SpaceRelationship"]] = relationship(
        "SpaceRelationship",
        foreign_keys="SpaceRelationship.child_space_id",
        back_populates="child_space",
    )
    inventory_slots: Mapped[list["Inventory"]] = relationship(
        "Inventory", back_populates="space", cascade="all, delete-orphan"
    )


class SpaceRelationship(Base):
    __tablename__ = "space_relationships"
    __table_args__ = (
        UniqueConstraint(
            "parent_space_id", "child_space_id", name="uq_space_relationships_parent_child"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    parent_space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False
    )
    child_space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False
    )
    relationship_type: Mapped[RelationshipType] = mapped_column(
        Enum(RelationshipType), nullable=False, default=RelationshipType.PARENT_CHILD
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    parent_space: Mapped["Space"] = relationship(
        "Space", foreign_keys=[parent_space_id], back_populates="children_rel"
    )
    child_space: Mapped["Space"] = relationship(
        "Space", foreign_keys=[child_space_id], back_populates="parents_rel"
    )


class Inventory(Base):
    __tablename__ = "inventory"
    __table_args__ = (
        UniqueConstraint(
            "space_id", "fecha", "hora_inicio", "hora_fin",
            name="uq_inventory_space_slot",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    hora_inicio: Mapped[time] = mapped_column(Time, nullable=False)
    hora_fin: Mapped[time] = mapped_column(Time, nullable=False)
    estado: Mapped[SlotStatus] = mapped_column(
        Enum(SlotStatus), nullable=False, default=SlotStatus.AVAILABLE
    )
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )  # FK to reservations when Tarea 4 exists
    # Semantically references crm.quotes.id when estado == SOFT_HOLD (no FK to avoid circular dep)
    quote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    ttl_frozen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    space: Mapped["Space"] = relationship("Space", back_populates="inventory_slots")


class SpaceBookingRule(Base):
    __tablename__ = "space_booking_rules"
    __table_args__ = (
        UniqueConstraint("space_id", name="uq_space_booking_rules_space"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    min_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    allowed_start_times: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
