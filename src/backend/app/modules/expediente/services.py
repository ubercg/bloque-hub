"""Servicio de Expediente Digital: append atómico con Chain of Trust (SHA-256)."""

from __future__ import annotations

import hashlib
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.expediente.models import ExpedienteDocument

if TYPE_CHECKING:
    pass


def _compute_chain_sha256(chain_prev_sha256: str | None, doc_sha256: str) -> str:
    """
    Hash_N = SHA256(chain_prev_sha256 + doc_sha256).
    Para el genesis, chain_prev_sha256 es el hash del primer documento (convención: prev = doc para el primero).
    """
    if chain_prev_sha256 is None:
        # Genesis: chain = SHA256(doc)
        payload = doc_sha256
    else:
        payload = chain_prev_sha256 + doc_sha256
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_last_chain_sha256(
    db: Session,
    *,
    reservation_id: uuid.UUID | None = None,
    contract_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID,
) -> str | None:
    """Obtiene el chain_sha256 del último documento del expediente para la reserva o contrato."""
    if reservation_id is not None:
        stmt = (
            select(ExpedienteDocument.chain_sha256)
            .where(
                ExpedienteDocument.tenant_id == tenant_id,
                ExpedienteDocument.reservation_id == reservation_id,
            )
            .order_by(ExpedienteDocument.created_at.desc())
            .limit(1)
        )
    elif contract_id is not None:
        stmt = (
            select(ExpedienteDocument.chain_sha256)
            .where(
                ExpedienteDocument.tenant_id == tenant_id,
                ExpedienteDocument.contract_id == contract_id,
            )
            .order_by(ExpedienteDocument.created_at.desc())
            .limit(1)
        )
    else:
        return None
    row = db.execute(stmt).scalars().first()
    return row


def append_document(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    document_type: str,
    doc_sha256: str,
    document_url: str | None = None,
    reservation_id: uuid.UUID | None = None,
    contract_id: uuid.UUID | None = None,
) -> ExpedienteDocument:
    """
    Añade un documento al expediente de forma atómica y calcula el nuevo eslabón de la cadena.
    reservation_id o contract_id debe ser proporcionado (uno de los dos).
    """
    if (reservation_id is None) == (contract_id is None):
        raise ValueError("Exactly one of reservation_id or contract_id must be set")

    chain_prev = get_last_chain_sha256(
        db, reservation_id=reservation_id, contract_id=contract_id, tenant_id=tenant_id
    )
    chain_sha256 = _compute_chain_sha256(chain_prev, doc_sha256)

    doc = ExpedienteDocument(
        tenant_id=tenant_id,
        reservation_id=reservation_id,
        contract_id=contract_id,
        document_type=document_type,
        document_url=document_url,
        doc_sha256=doc_sha256,
        chain_prev_sha256=chain_prev,
        chain_sha256=chain_sha256,
    )
    db.add(doc)
    db.flush()
    return doc
