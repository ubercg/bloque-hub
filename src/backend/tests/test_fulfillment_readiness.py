"""Tests for fulfillment readiness and evidence (Buzón de Evidencias)."""

import uuid
from datetime import date, datetime, time, timezone

import pytest
from sqlalchemy.orm import Session

from app.db.session import get_db_context
from app.modules.booking.models import Reservation, ReservationStatus
from app.modules.fulfillment.models import (
    Checklist,
    EvidenceRequirement,
    EvidenceStatus,
    MasterServiceOrder,
    MasterServiceOrderStatus,
    ServiceOrderItem,
    ServiceOrderItemStatus,
)
from app.modules.fulfillment.services import get_readiness
from app.modules.identity.models import Tenant, User, UserRole
from app.modules.inventory.models import BookingMode, Space


@pytest.fixture
def space_a(tenant_a: Tenant, db_super: Session) -> Space:
    uid = uuid.uuid4().hex[:8]
    s = Space(
        tenant_id=tenant_a.id,
        name="Sala A",
        slug=f"sala-a-{uid}",
        booking_mode=BookingMode.SEMI_DIRECT,
        capacidad_maxima=10,
        precio_por_hora=100,
        ttl_minutos=60,
    )
    db_super.add(s)
    db_super.commit()
    db_super.refresh(s)
    return s


@pytest.fixture
def reservation_a(
    tenant_a: Tenant, user_operations_a: User, space_a: Space, db_super: Session
) -> Reservation:
    r = Reservation(
        tenant_id=tenant_a.id,
        user_id=user_operations_a.id,
        space_id=space_a.id,
        fecha=date(2026, 3, 15),
        hora_inicio=time(10, 0),
        hora_fin=time(12, 0),
        status=ReservationStatus.CONFIRMED,
    )
    db_super.add(r)
    db_super.commit()
    db_super.refresh(r)
    return r


@pytest.fixture
def reservation_customer_owned(
    tenant_a: Tenant, user_a: User, space_a: Space, db_super: Session
) -> Reservation:
    """Reservation owned by CUSTOMER user_a (for portal/evidence tests)."""
    r = Reservation(
        tenant_id=tenant_a.id,
        user_id=user_a.id,
        space_id=space_a.id,
        fecha=date(2026, 4, 1),
        hora_inicio=time(14, 0),
        hora_fin=time(16, 0),
        status=ReservationStatus.CONFIRMED,
    )
    db_super.add(r)
    db_super.commit()
    db_super.refresh(r)
    return r


@pytest.fixture
def service_order_with_evidence(
    tenant_a: Tenant, reservation_a: Reservation, db_super: Session
) -> MasterServiceOrder:
    order = MasterServiceOrder(
        tenant_id=tenant_a.id,
        reservation_id=reservation_a.id,
        contract_id=None,
        status=MasterServiceOrderStatus.IN_PROGRESS,
    )
    db_super.add(order)
    db_super.flush()
    checklist = Checklist(
        master_service_order_id=order.id,
        name="Preparación",
        item_order=0,
    )
    db_super.add(checklist)
    db_super.flush()
    db_super.add(
        ServiceOrderItem(
            checklist_id=checklist.id,
            title="Critical task",
            item_order=0,
            is_critical=True,
            status=ServiceOrderItemStatus.PENDING,
        )
    )
    db_super.add(
        ServiceOrderItem(
            checklist_id=checklist.id,
            title="Optional task",
            item_order=1,
            is_critical=False,
            status=ServiceOrderItemStatus.PENDING,
        )
    )
    plazo = datetime(2026, 3, 10, tzinfo=timezone.utc)
    for tipo in ("INE_RESPONSABLE", "CARTA_RESPONSIVA"):
        db_super.add(
            EvidenceRequirement(
                tenant_id=tenant_a.id,
                master_service_order_id=order.id,
                tipo_documento=tipo,
                estado=EvidenceStatus.PENDIENTE,
                plazo_vence_at=plazo,
            )
        )
    db_super.commit()
    db_super.refresh(order)
    return order


@pytest.mark.integration
def test_get_readiness_not_ready(
    service_order_with_evidence: MasterServiceOrder, db_super: Session
) -> None:
    """Readiness is False when critical item and evidence are pending."""
    with get_db_context(
        tenant_id=str(service_order_with_evidence.tenant_id), role=None
    ) as db:
        result = get_readiness(service_order_with_evidence.id, db)
    assert result is not None
    is_ready, checklist_pct, evidence_complete, details = result
    assert is_ready is False
    assert checklist_pct == 0.0  # 0/1 critical completed
    assert evidence_complete is False
    assert len(details["pending_critical_items"]) == 1
    assert len(details["pending_evidence"]) == 2


@pytest.mark.integration
def test_readiness_endpoint_and_evidence_flow(
    client,
    token_operations_a: str,
    service_order_with_evidence: MasterServiceOrder,
) -> None:
    """E2E: GET readiness, complete item, upload evidence, approve, GET readiness -> is_ready."""
    headers = {"Authorization": f"Bearer {token_operations_a}"}
    order_id = str(service_order_with_evidence.id)

    # GET readiness -> not ready
    r = client.get(f"/api/service-orders/{order_id}/readiness", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["is_ready"] is False
    assert data["evidence_complete"] is False

    # Get first critical item id from order
    r_order = client.get(f"/api/service-orders/{order_id}", headers=headers)
    assert r_order.status_code == 200
    items = [i for c in r_order.json()["checklists"] for i in c["items"] if i["is_critical"]]
    assert len(items) == 1
    item_id = items[0]["id"]

    # PATCH item to COMPLETED
    r_patch = client.patch(
        f"/api/service-order-items/{item_id}",
        json={"status": "COMPLETED"},
        headers=headers,
    )
    assert r_patch.status_code == 200

    # Readiness still False (evidence pending)
    r2 = client.get(f"/api/service-orders/{order_id}/readiness", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["is_ready"] is False
    assert r2.json()["checklist_pct"] == 100.0

    # List evidence and approve both (upload first for each type)
    r_ev = client.get(f"/api/service-orders/{order_id}/evidence", headers=headers)
    assert r_ev.status_code == 200
    ev_list = r_ev.json()
    assert len(ev_list) == 2

    # Upload file for INE_RESPONSABLE
    pdf_bytes = b"%PDF-1.4 minimal"
    r_upload1 = client.post(
        f"/api/service-orders/{order_id}/evidence",
        data={"tipo_documento": "INE_RESPONSABLE"},
        files={"file": ("ine.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )
    assert r_upload1.status_code == 201
    ev1_id = r_upload1.json()["id"]

    # Approve first evidence
    r_rev1 = client.patch(
        f"/api/service-order-evidence/{ev1_id}",
        json={"estado": "APROBADO"},
        headers=headers,
    )
    assert r_rev1.status_code == 200

    # Upload and approve CARTA_RESPONSIVA
    r_upload2 = client.post(
        f"/api/service-orders/{order_id}/evidence",
        data={"tipo_documento": "CARTA_RESPONSIVA"},
        files={"file": ("carta.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )
    assert r_upload2.status_code == 201
    ev2_id = r_upload2.json()["id"]
    r_rev2 = client.patch(
        f"/api/service-order-evidence/{ev2_id}",
        json={"estado": "APROBADO"},
        headers=headers,
    )
    assert r_rev2.status_code == 200

    # Now readiness should be True and OS status READY
    r3 = client.get(f"/api/service-orders/{order_id}/readiness", headers=headers)
    assert r3.status_code == 200
    assert r3.json()["is_ready"] is True
    assert r3.json()["evidence_complete"] is True

    r_order2 = client.get(f"/api/service-orders/{order_id}", headers=headers)
    assert r_order2.status_code == 200
    assert r_order2.json()["status"] == "READY"


@pytest.mark.integration
def test_operations_can_get_service_order_and_evidence_by_reservation(
    client,
    token_operations_a: str,
    reservation_a: Reservation,
    service_order_with_evidence: MasterServiceOrder,
) -> None:
    """OPERATIONS can GET /reservations/{id}/service-order and list evidence-requirements."""
    headers = {"Authorization": f"Bearer {token_operations_a}"}
    rid = str(reservation_a.id)
    r = client.get(f"/api/reservations/{rid}/service-order", headers=headers)
    assert r.status_code == 200
    assert r.json()["id"] == str(service_order_with_evidence.id)
    r_ev = client.get(f"/api/reservations/{rid}/evidence-requirements", headers=headers)
    assert r_ev.status_code == 200
    assert len(r_ev.json()) == 2


@pytest.mark.integration
def test_customer_can_delete_evidence_to_reupload(
    client,
    token_a: str,
    reservation_customer_owned: Reservation,
    tenant_a,
    db_super: Session,
) -> None:
    """CUSTOMER (owner) can DELETE evidence in PENDIENTE_REVISION to re-upload."""
    from pathlib import Path

    from app.core.config import settings
    from app.modules.fulfillment.models import (
        EvidenceRequirement,
        EvidenceStatus,
        MasterServiceOrder,
        MasterServiceOrderStatus,
    )
    from app.modules.fulfillment.services import create_os_for_reservation

    create_os_for_reservation(reservation_customer_owned, db_super)
    order = (
        db_super.query(MasterServiceOrder)
        .filter(
            MasterServiceOrder.reservation_id == reservation_customer_owned.id,
            MasterServiceOrder.tenant_id == tenant_a.id,
        )
        .first()
    )
    assert order is not None
    ev = (
        db_super.query(EvidenceRequirement)
        .filter(
            EvidenceRequirement.master_service_order_id == order.id,
            EvidenceRequirement.tipo_documento == "INE_RESPONSABLE",
        )
        .first()
    )
    assert ev is not None
    storage = Path(settings.EVIDENCE_STORAGE_PATH)
    storage.mkdir(parents=True, exist_ok=True)
    ev.file_path = f"{ev.id}.pdf"
    ev.filename = "ine.pdf"
    ev.estado = EvidenceStatus.PENDIENTE_REVISION
    ev.uploaded_at = datetime.now(timezone.utc)
    db_super.commit()
    (storage / ev.file_path).write_bytes(b"%PDF minimal")

    headers = {"Authorization": f"Bearer {token_a}"}
    rid = str(reservation_customer_owned.id)
    ev_id = str(ev.id)
    r = client.delete(f"/api/reservations/{rid}/evidence/{ev_id}", headers=headers)
    assert r.status_code == 204

    db_super.refresh(ev)
    assert ev.estado == EvidenceStatus.PENDIENTE
    assert ev.file_path is None
    assert ev.filename is None
