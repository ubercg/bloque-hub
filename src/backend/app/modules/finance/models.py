import enum
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Boolean, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CfdiTipo(str, enum.Enum):
    INGRESO = "INGRESO"


class CfdiEstado(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    TIMBRADO = "TIMBRADO"
    ERROR = "ERROR"
    CANCELADO = "CANCELADO"


class CfdiDocument(Base):
    __tablename__ = "cfdi_documents"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    reservation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("reservations.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False, server_default="INGRESO")
    uuid_fiscal: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    rfc_emisor: Mapped[str] = mapped_column(String(20), nullable=False)
    rfc_receptor: Mapped[str] = mapped_column(String(20), nullable=False)
    razon_social_receptor: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    regimen_receptor: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    uso_cfdi: Mapped[str] = mapped_column(String(5), nullable=False, server_default="G03")
    forma_pago: Mapped[str] = mapped_column(String(5), nullable=False)
    monto: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    iva_monto: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    xml_url: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    pdf_url: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PENDIENTE", index=True)
    timbrado_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duracion_timbrado_ms: Mapped[Optional[int]] = mapped_column(Integer(), nullable=True)
    cancelado_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_codigo: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    error_descripcion: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    intentos_timbrado: Mapped[int] = mapped_column(Integer(), nullable=False, server_default="0")
    ultimo_intento_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CreditBalance(Base):
    __tablename__ = "credit_balances"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    cfdi_uuid: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    monto_original: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    saldo_restante: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    reservation_origen_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("reservations.id", ondelete="SET NULL"), nullable=True)
    aplicado_a_reservation_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("reservations.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Reconciliation(Base):
    __tablename__ = "reconciliations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    description: Mapped[str] = mapped_column(String(255))
    amount: Mapped[float]
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[Optional[UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Reconciliation {self.id} - Tenant {self.tenant_id} - Approved: {self.is_approved}>"
