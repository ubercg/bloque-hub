import pytest
from uuid import uuid4
from app.modules.fulfillment.services import check_ready_gate
from app.modules.fulfillment.models import ServiceOrder, ServiceOrderType, ServiceOrderStatus, ChecklistItem
from app.modules.booking.services import create_phased_reservation
from app.modules.booking.models import EventPhase
from app.modules.inventory.models import Space
from datetime import date, time, datetime

def test_ready_gate_blocked_by_critical_checklist(db_super, tenant_a, user_a):
    space1 = Space(tenant_id=tenant_a.id, name="Space Gating", slug="space-gating", capacidad_maxima=10, precio_por_hora=100)
    db_super.add(space1)
    db_super.commit()

    today = date.today()
    start_dt = datetime.combine(today, time(10, 0))
    end_dt = datetime.combine(today, time(12, 0))

    # Create MONTAJE reservation
    res = create_phased_reservation(
        tenant_id=tenant_a.id,
        user_id=user_a.id,
        space_id=space1.id,
        slots=[(start_dt, end_dt)],
        phase=EventPhase.MONTAJE,
        db=db_super,
    )
    
    # Create a ServiceOrder for AUDIO
    so = ServiceOrder(
        tenant_id=tenant_a.id,
        reservation_id=res.id,
        type=ServiceOrderType.AUDIO,
        status=ServiceOrderStatus.PENDING,
    )
    db_super.add(so)
    db_super.flush()
    
    # Add a critical checklist item that is NOT completed
    item = ChecklistItem(
        tenant_id=tenant_a.id,
        service_order_id=so.id,
        description="Verificar consolas",
        is_critical=True,
        completed=False,
    )
    db_super.add(item)
    db_super.flush()
    
    is_ready, pending = check_ready_gate(res.id, db_super)
    assert is_ready is False
    assert "Verificar consolas" in pending
    assert res.ready_blocked is True


def test_ready_gate_passes_when_all_critical_complete(db_super, tenant_a, user_a):
    space1 = Space(tenant_id=tenant_a.id, name="Space Gating 2", slug="space-gating-2", capacidad_maxima=10, precio_por_hora=100)
    db_super.add(space1)
    db_super.commit()

    today = date.today()
    start_dt = datetime.combine(today, time(10, 0))
    end_dt = datetime.combine(today, time(12, 0))

    # Create MONTAJE reservation
    res = create_phased_reservation(
        tenant_id=tenant_a.id,
        user_id=user_a.id,
        space_id=space1.id,
        slots=[(start_dt, end_dt)],
        phase=EventPhase.MONTAJE,
        db=db_super,
    )
    
    # Create a ServiceOrder for VIDEO
    so = ServiceOrder(
        tenant_id=tenant_a.id,
        reservation_id=res.id,
        type=ServiceOrderType.VIDEO,
        status=ServiceOrderStatus.PENDING,
    )
    db_super.add(so)
    db_super.flush()
    
    # Add a critical checklist item that IS completed
    item = ChecklistItem(
        tenant_id=tenant_a.id,
        service_order_id=so.id,
        description="Instalar proyector",
        is_critical=True,
        completed=True,
    )
    db_super.add(item)
    
    # Add a NON-critical item NOT completed
    item2 = ChecklistItem(
        tenant_id=tenant_a.id,
        service_order_id=so.id,
        description="Cables extra",
        is_critical=False,
        completed=False,
    )
    db_super.add(item2)
    db_super.flush()
    
    is_ready, pending = check_ready_gate(res.id, db_super)
    assert is_ready is True
    assert len(pending) == 0
    assert res.ready_blocked is False

