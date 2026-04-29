"""Expediente Digital: modelo append-only con cadena de hashes (NOM-151)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExpedienteDocument(Base):
    """
    Documento en el Expediente Digital Único. Append-only.
    Cadena: chain_sha256 = SHA256(chain_prev_sha256 + doc_sha256); genesis tiene chain_prev_sha256 NULL.
    """

    __tablename__ = "expediente_documents"
    __table_args__ = (
        CheckConstraint(
            "reservation_id IS NOT NULL OR contract_id IS NOT NULL",
            name="chk_expediente_reservation_or_contract",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reservations.id", ondelete="CASCADE"), nullable=True
    )
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contracts.id", ondelete="CASCADE"), nullable=True
    )
    document_type: Mapped[str] = mapped_column(String(64), nullable=False)
    document_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    doc_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    chain_prev_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chain_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
