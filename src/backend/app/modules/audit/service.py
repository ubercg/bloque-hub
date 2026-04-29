"""Append-only audit log writer. Never update or delete."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.audit.models import AuditLog


def append_audit_log(
    db: Session,
    tenant_id: UUID,
    tabla: str,
    registro_id: UUID,
    accion: str,
    *,
    campo_modificado: str | None = None,
    valor_anterior: dict | None = None,
    valor_nuevo: dict | None = None,
    actor_id: UUID | None = None,
    actor_ip: str | None = None,
    actor_user_agent: str | None = None,
    correlacion_id: UUID | None = None,
) -> None:
    """Append one audit record. Caller is responsible for commit; we only flush."""
    entry = AuditLog(
        tenant_id=tenant_id,
        tabla=tabla,
        registro_id=registro_id,
        accion=accion,
        campo_modificado=campo_modificado,
        valor_anterior=valor_anterior,
        valor_nuevo=valor_nuevo,
        actor_id=actor_id,
        actor_ip=actor_ip,
        actor_user_agent=actor_user_agent,
        correlacion_id=correlacion_id,
    )
    db.add(entry)
    db.flush()
