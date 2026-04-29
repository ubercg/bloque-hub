import uuid
from datetime import datetime
from sqlalchemy import ForeignKey, String, Numeric, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class PaymentReference(Base):
    __tablename__ = "payment_references"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    reservation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reservations.id"), index=True)
    reference_code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING, PAID, FAILED
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)