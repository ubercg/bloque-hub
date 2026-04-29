from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Time, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ReservationStatus(str, enum.Enum):
    PENDING_SLIP = "PENDING_SLIP"
    AWAITING_PAYMENT = "AWAITING_PAYMENT"
    PAYMENT_UNDER_REVIEW = "PAYMENT_UNDER_REVIEW"
    CONFIRMED = "CONFIRMED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False
    )
    group_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    discount_code_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("discount_codes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    discount_amount_applied: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    event_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    hora_inicio: Mapped[time] = mapped_column(Time, nullable=False)
    hora_fin: Mapped[time] = mapped_column(Time, nullable=False)
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(ReservationStatus), nullable=False, default=ReservationStatus.PENDING_SLIP
    )
    ttl_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ttl_frozen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_from_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    device_fingerprint: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", foreign_keys=[tenant_id])
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    space: Mapped["Space"] = relationship("Space", foreign_keys=[space_id])
    payment_vouchers: Mapped[list["PaymentVoucher"]] = relationship(
        "PaymentVoucher", back_populates="reservation", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Reservation(id={self.id}, status={self.status})>"


class PaymentVoucher(Base):
    """Payment voucher (comprobante de pago SPEI) uploaded by customer."""

    __tablename__ = "payment_vouchers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    reservation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reservations.id", ondelete="CASCADE"), nullable=False
    )
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_kb: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    uploaded_by_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    reservation: Mapped["Reservation"] = relationship(
        "Reservation", back_populates="payment_vouchers"
    )
    tenant: Mapped["Tenant"] = relationship("Tenant", foreign_keys=[tenant_id])

    def __repr__(self) -> str:
        return f"<PaymentVoucher(id={self.id}, reservation_id={self.reservation_id})>"
