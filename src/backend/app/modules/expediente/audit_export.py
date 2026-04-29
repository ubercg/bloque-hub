"""Exportación Audit-Ready: ZIP con manifest de documentos y certificado de integridad."""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.expediente.models import ExpedienteDocument


def build_audit_package(
    db: Session,
    *,
    reservation_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> bytes:
    """
    Genera un ZIP con manifest de documentos del expediente y certificado de integridad.
    Objetivo: < 30 s. No incluye contenido de archivos (solo metadata e hashes).
    """
    stmt = (
        select(ExpedienteDocument)
        .where(
            ExpedienteDocument.tenant_id == tenant_id,
            ExpedienteDocument.reservation_id == reservation_id,
        )
        .order_by(ExpedienteDocument.created_at.asc())
    )
    docs = list(db.execute(stmt).scalars().all())
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Manifest: un registro por documento
        lines = [
            "document_id;document_type;doc_sha256;chain_prev_sha256;chain_sha256;created_at;document_url",
        ]
        last_chain: str | None = None
        for d in docs:
            lines.append(
                f"{d.id};{d.document_type};{d.doc_sha256};{d.chain_prev_sha256 or ''};{d.chain_sha256};{d.created_at.isoformat() if d.created_at else ''};{d.document_url or ''}"
            )
            last_chain = d.chain_sha256
        zf.writestr("manifest.csv", "\n".join(lines))
        # Certificado de integridad (último eslabón de la cadena)
        zf.writestr(
            "certificado_integridad.txt",
            f"Expediente Digital — Reserva {reservation_id}\n"
            f"Generado: {datetime.now(timezone.utc).isoformat()}\n"
            f"Documentos: {len(docs)}\n"
            f"Chain SHA256 (último eslabón): {last_chain or 'N/A'}\n",
        )
    buf.seek(0)
    return buf.read()


def get_audit_package_last_chain(
    db: Session,
    *,
    reservation_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> str | None:
    """Devuelve el chain_sha256 del último documento (para verificación)."""
    stmt = (
        select(ExpedienteDocument.chain_sha256)
        .where(
            ExpedienteDocument.tenant_id == tenant_id,
            ExpedienteDocument.reservation_id == reservation_id,
        )
        .order_by(ExpedienteDocument.created_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalars().first()
