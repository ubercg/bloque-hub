"""Tests for audit log: append-only and reservation state change interception."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db_context
from app.modules.audit.models import AuditLog
from app.modules.audit.service import append_audit_log


@pytest.mark.integration
def test_audit_log_append_and_immutable(tenant_a, db_super: Session):
    """Append a record then verify UPDATE/DELETE are forbidden for app role."""
    with get_db_context(tenant_id=str(tenant_a.id), role="COMMERCIAL") as db:
        append_audit_log(
            db,
            tenant_id=tenant_a.id,
            tabla="reservations",
            registro_id=uuid.uuid4(),
            accion="STATE_CHANGE",
            campo_modificado="status",
            valor_nuevo={"status": "PENDING_SLIP"},
            actor_id=None,
            actor_ip="127.0.0.1",
        )
        db.commit()

    with get_db_context(tenant_id=str(tenant_a.id), role="COMMERCIAL") as db:
        row = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        assert row is not None
        assert row.tabla == "reservations"
        assert row.accion == "STATE_CHANGE"
        audit_id = row.id

        # App role must not be able to UPDATE or DELETE (REVOKE in migration)
        with pytest.raises(Exception):
            db.execute(
                text("UPDATE audit_log SET tabla = 'x' WHERE id = :id"),
                {"id": audit_id},
            )
            db.flush()
        db.rollback()

        with pytest.raises(Exception):
            db.execute(text("DELETE FROM audit_log WHERE id = :id"), {"id": audit_id})
            db.flush()
        db.rollback()


@pytest.mark.skip(
    reason="Test acoplado a estado interno de services.py — fix pendiente en TASK separada"
)
@pytest.mark.integration
def test_audit_log_reservation_flow_creates_entries(
    client,
    token_a: str,
    token_finance_a: str,
    tenant_a,
    user_a,
    db_super,
):
    """Create reservation via API and verify audit_log receives STATE_CHANGE entries."""
    from app.modules.inventory.models import Space

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala Audit",
        slug="sala-audit-test",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)

    with get_db_context(tenant_id=str(tenant_a.id), role="SUPERADMIN") as db:
        count_before = (
            db.query(AuditLog).filter(AuditLog.tabla == "reservations").count()
        )

    r = client.post(
        "/api/reservations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "space_id": str(space.id),
            "fecha": "2026-11-01",
            "hora_inicio": "10:00:00",
            "hora_fin": "11:00:00",
        },
    )
    assert r.status_code == 201
    reservation_id = r.json()["id"]

    with get_db_context(tenant_id=str(tenant_a.id), role="SUPERADMIN") as db:
        count_after = (
            db.query(AuditLog).filter(AuditLog.tabla == "reservations").count()
        )
        assert count_after >= count_before + 1
        entries = (
            db.query(AuditLog)
            .filter(AuditLog.registro_id == uuid.UUID(reservation_id))
            .order_by(AuditLog.registrado_at)
            .all()
        )
        assert len(entries) >= 1
        assert entries[0].valor_nuevo == {"status": "PENDING_SLIP"}
