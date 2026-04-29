from sqlalchemy import (
    Column,
    String,
    Numeric,
    ForeignKey,
    Enum,
    Boolean,
    DateTime,
    func,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
import enum
import uuid
from datetime import datetime
from app.db.base import Base


class ServiceUnit(str, enum.Enum):
    MINUTO = "MINUTO"
    EVENTO = "EVENTO"
    M2 = "M2"


class AdditionalService(Base):
    __tablename__ = "additional_services"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[ServiceUnit] = mapped_column(
        Enum(ServiceUnit), nullable=False, default=ServiceUnit.EVENTO
    )
    unit_price: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    factor: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
