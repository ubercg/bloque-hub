from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, String, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func

from app.db.base import Base


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    tenant_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    user_id = Column(PG_UUID(as_uuid=True), nullable=True, index=True)  # Null for failed attempts before user identification
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    status = Column(String, nullable=False)  # e.g., 'SUCCESS', 'FAILURE'

    def __repr__(self):
        return f"<LoginAttempt(id={self.id}, tenant_id={self.tenant_id}, user_id={self.user_id}, status='{self.status}')>"


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(sa.BigInteger, primary_key=True, autoincrement=True)
    tenant_id = Column(PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    tabla = Column(String(100), nullable=False)
    registro_id = Column(PG_UUID(as_uuid=True), nullable=False)
    accion = Column(String(20), nullable=False) # e.g. 'CREATE', 'UPDATE', 'DELETE'
    campo_modificado = Column(String(100), nullable=True)
    valor_anterior = Column(JSONB, nullable=True)
    valor_nuevo = Column(JSONB, nullable=True)
    actor_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_ip = Column(String(45), nullable=True)
    actor_user_agent = Column(sa.Text, nullable=True)
    correlacion_id = Column(PG_UUID(as_uuid=True), nullable=True)
    registrado_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)

    def __repr__(self):
        return f"<AuditLog(id={self.id}, tabla={self.tabla}, accion={self.accion})>"
