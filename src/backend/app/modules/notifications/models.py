"""Modelos del módulo de notificaciones (log de envíos, mensajes del portal)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NotificationLog(Base):
    """Registro de notificaciones enviadas (evita reenviar recordatorio TTL, etc.)."""

    __tablename__ = "notification_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    reservation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reservations.id", ondelete="CASCADE"), nullable=False
    )
    notification_type: Mapped[str] = mapped_column(String(64), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RemitenteTipo(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    STAFF = "STAFF"


class PortalMessage(Base):
    """Mensajes bidireccionales Cliente ↔ Staff en el Portal (FR-25)."""

    __tablename__ = "portal_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    reservation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reservations.id", ondelete="CASCADE"), nullable=False
    )
    remitente_tipo: Mapped[str] = mapped_column(String(32), nullable=False)  # CUSTOMER | STAFF
    remitente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    enviado_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    leido_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
