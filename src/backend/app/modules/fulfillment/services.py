"""Fulfillment services: create OS for reservation or contract with default checklists."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.modules.booking.models import Reservation
from app.modules.crm.models import Contract
from app.modules.fulfillment.models import (
    Checklist,
    EvidenceRequirement,
    EvidenceStatus,
    MasterServiceOrder,
    MasterServiceOrderStatus,
    ServiceOrderItem,
    ServiceOrderItemStatus,
    ServiceOrder,
    ServiceOrderStatus,
    ChecklistItem,
)

DEFAULT_CHECKLIST_NAME = "Preparación"
DEFAULT_ITEMS = [
    "Verificar espacio disponible",
    "Confirmar equipamiento",
    "Apertura de acceso",
]
CONTRACT_CHECKLIST_NAME = "Preparación evento bajo contrato"

# Default evidence document types created per OS (FR-26 minimal set)
DEFAULT_EVIDENCE_TIPOS = ("INE_RESPONSABLE", "CARTA_RESPONSIVA")


def _plazo_vence_from_event_date(event_date: date | None) -> datetime:
    """Plazo for evidence: 5 days before event, or 30 days from now if no date."""
    if event_date:
        return datetime.combine(
            event_date - timedelta(days=5),
            datetime.min.time(),
            tzinfo=timezone.utc,
        )
    return datetime.now(timezone.utc) + timedelta(days=30)


def _add_default_evidence_requirements(
    order: MasterServiceOrder, plazo_vence_at: datetime, db: Session
) -> None:
    for tipo in DEFAULT_EVIDENCE_TIPOS:
        db.add(
            EvidenceRequirement(
                tenant_id=order.tenant_id,
                master_service_order_id=order.id,
                tipo_documento=tipo,
                estado=EvidenceStatus.PENDIENTE,
                plazo_vence_at=plazo_vence_at,
            )
        )
    db.flush()


def _add_default_checklist_and_items(order: MasterServiceOrder, db: Session) -> None:
    checklist = Checklist(
        master_service_order_id=order.id,
        name=DEFAULT_CHECKLIST_NAME,
        item_order=0,
    )
    db.add(checklist)
    db.flush()
    for i, title in enumerate(DEFAULT_ITEMS):
        db.add(
            ServiceOrderItem(
                checklist_id=checklist.id,
                title=title,
                item_order=i,
                status=ServiceOrderItemStatus.PENDING,
            )
        )
    db.flush()


def create_os_for_reservation(
    reservation: Reservation, db: Session
) -> MasterServiceOrder:
    """Create MasterServiceOrder and default checklist/items for a confirmed reservation."""
    order = MasterServiceOrder(
        tenant_id=reservation.tenant_id,
        reservation_id=reservation.id,
        contract_id=None,
        status=MasterServiceOrderStatus.PENDING,
    )
    db.add(order)
    db.flush()
    _add_default_checklist_and_items(order, db)
    plazo = _plazo_vence_from_event_date(reservation.fecha)
    _add_default_evidence_requirements(order, plazo, db)
    return order


def create_os_for_contract(contract: Contract, db: Session) -> MasterServiceOrder:
    """Create MasterServiceOrder and default checklist/items for a signed contract."""
    order = MasterServiceOrder(
        tenant_id=contract.tenant_id,
        reservation_id=None,
        contract_id=contract.id,
        status=MasterServiceOrderStatus.PENDING,
    )
    db.add(order)
    db.flush()
    checklist = Checklist(
        master_service_order_id=order.id,
        name=CONTRACT_CHECKLIST_NAME,
        item_order=0,
    )
    db.add(checklist)
    db.flush()
    for i, title in enumerate(DEFAULT_ITEMS):
        db.add(
            ServiceOrderItem(
                checklist_id=checklist.id,
                title=title,
                item_order=i,
                status=ServiceOrderItemStatus.PENDING,
            )
        )
    db.flush()
    # Event date from earliest quote item if available
    event_date: date | None = None
    if contract.quote_id and contract.quote:
        items = list(contract.quote.items) if contract.quote.items else []
        if items:
            event_date = min(qi.fecha for qi in items)
    plazo = _plazo_vence_from_event_date(event_date)
    _add_default_evidence_requirements(order, plazo, db)
    return order


def _readiness_result(order: MasterServiceOrder) -> tuple[bool, float, bool, dict]:
    """Pure computation of readiness from an order (checklists and evidence loaded)."""
    critical_items = [i for c in order.checklists for i in c.items if i.is_critical]
    critical_total = len(critical_items)
    critical_completed = sum(
        1 for i in critical_items if i.status == ServiceOrderItemStatus.COMPLETED
    )
    checklist_pct = (
        (critical_completed / critical_total * 100.0) if critical_total else 100.0
    )

    evidence_list = order.evidence_requirements or []
    evidence_total = len(evidence_list)
    evidence_approved = sum(
        1 for e in evidence_list if e.estado == EvidenceStatus.APROBADO
    )
    evidence_complete = evidence_total == evidence_approved if evidence_total else True

    is_ready = (
        critical_total == 0 or critical_completed == critical_total
    ) and evidence_complete

    pending_items = [
        {"id": str(i.id), "title": i.title}
        for c in order.checklists
        for i in c.items
        if i.is_critical and i.status != ServiceOrderItemStatus.COMPLETED
    ]
    pending_evidence = [
        {"id": str(e.id), "tipo_documento": e.tipo_documento}
        for e in evidence_list
        if e.estado != EvidenceStatus.APROBADO
    ]
    details = {
        "pending_critical_items": pending_items,
        "pending_evidence": pending_evidence,
    }
    return is_ready, checklist_pct, evidence_complete, details


def get_readiness(order_id: UUID, db: Session) -> tuple[bool, float, bool, dict] | None:
    """
    Return readiness for a service order (read-only).
    Returns (is_ready, checklist_pct, evidence_complete, details) or None if order not found.
    """
    order = (
        db.query(MasterServiceOrder)
        .options(
            joinedload(MasterServiceOrder.checklists).joinedload(Checklist.items),
            joinedload(MasterServiceOrder.evidence_requirements),
        )
        .filter(MasterServiceOrder.id == order_id)
        .first()
    )
    if not order:
        return None
    return _readiness_result(order)


def get_readiness_by_reservation_id(
    reservation_id: UUID, db: Session
) -> tuple[bool, float, bool, dict] | None:
    """
    Return readiness for the service order linked to this reservation (1:1).
    Returns (is_ready, checklist_pct, evidence_complete, details) or None if no OS found.
    Used by Gate (validate-qr) and optionally by other clients.
    """
    order = (
        db.query(MasterServiceOrder)
        .options(
            joinedload(MasterServiceOrder.checklists).joinedload(Checklist.items),
            joinedload(MasterServiceOrder.evidence_requirements),
        )
        .filter(MasterServiceOrder.reservation_id == reservation_id)
        .first()
    )
    if not order:
        return None
    return _readiness_result(order)


def check_ready_gate(reservation_id: UUID, db: Session) -> tuple[bool, list[str]]:
    """
    Check if a MONTAJE phase reservation can proceed to READY status (FR-39).
    Returns (is_ready, pending_critical_items).
    If not ready, sets ready_blocked=True on the reservation and emits an event.
    """
    reservation = db.get(Reservation, reservation_id)
    if not reservation:
        return False, ["Reservation not found"]

    orders = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.reservation_id == reservation_id)
        .all()
    )

    pending_items = []
    for order in orders:
        for item in order.checklist_items:
            if item.is_critical and not item.completed:
                pending_items.append(item.description)

    is_ready = len(pending_items) == 0

    if not is_ready and not reservation.ready_blocked:
        reservation.ready_blocked = True
        db.flush()
        # Stub for EventStore notification (T5/Celery integration)
        # In a real app we'd dispatch MONTAJE_NO_INICIADO
        pass
    elif is_ready and reservation.ready_blocked:
        reservation.ready_blocked = False
        db.flush()

    return is_ready, pending_items


def compute_readiness(order_id: UUID, db: Session) -> tuple[bool, float, bool, dict]:
    """
    Compute readiness and, if is_ready, transition order to READY.
    Returns (is_ready, checklist_pct, evidence_complete, details).
    """
    order = (
        db.query(MasterServiceOrder)
        .options(
            joinedload(MasterServiceOrder.checklists).joinedload(Checklist.items),
            joinedload(MasterServiceOrder.evidence_requirements),
        )
        .filter(MasterServiceOrder.id == order_id)
        .first()
    )
    if not order:
        return False, 0.0, False, {"error": "Order not found"}

    is_ready, checklist_pct, evidence_complete, details = _readiness_result(order)
    if is_ready and order.status in (
        MasterServiceOrderStatus.PENDING,
        MasterServiceOrderStatus.IN_PROGRESS,
    ):
        order.status = MasterServiceOrderStatus.READY
    return is_ready, checklist_pct, evidence_complete, details
