import pytest
from datetime import date, time, timedelta, datetime
from app.modules.booking.services import create_phased_reservation, ConflictException
from app.modules.booking.models import ReservationStatus, EventPhase
from app.modules.inventory.models import Space


def test_montaje_anti_overlap_strict(db_super, tenant_a, user_a):
    space1 = Space(
        tenant_id=tenant_a.id,
        name="Space M",
        slug="space-m",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space1)
    db_super.commit()

    today = date.today()
    dt_uso_start = datetime.combine(today, time(14, 0))
    dt_uso_end = datetime.combine(today, time(18, 0))

    res1 = create_phased_reservation(
        tenant_id=tenant_a.id,
        user_id=user_a.id,
        space_id=space1.id,
        slots=[(dt_uso_start, dt_uso_end)],
        phase=EventPhase.USO,
        db=db_super,
    )

    dt_montaje_start = datetime.combine(today, time(16, 0))
    dt_montaje_end = datetime.combine(today, time(20, 0))

    with pytest.raises(ConflictException, match="Overlap with MONTAJE"):
        create_phased_reservation(
            tenant_id=tenant_a.id,
            user_id=user_a.id,
            space_id=space1.id,
            slots=[(dt_montaje_start, dt_montaje_end)],
            phase=EventPhase.MONTAJE,
            db=db_super,
        )


def test_desmontaje_can_overlap_next_montaje(db_super, tenant_a, user_a):
    space1 = Space(
        tenant_id=tenant_a.id,
        name="Space D",
        slug="space-d",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space1)
    db_super.commit()

    today = date.today()
    dt_d_start = datetime.combine(today, time(18, 0))
    dt_d_end = datetime.combine(today, time(22, 0))

    create_phased_reservation(
        tenant_id=tenant_a.id,
        user_id=user_a.id,
        space_id=space1.id,
        slots=[(dt_d_start, dt_d_end)],
        phase=EventPhase.DESMONTAJE,
        db=db_super,
    )

    dt_m_start = datetime.combine(today, time(20, 0))
    dt_m_end = datetime.combine(today, time(23, 0))

    res_m = create_phased_reservation(
        tenant_id=tenant_a.id,
        user_id=user_a.id,
        space_id=space1.id,
        slots=[(dt_m_start, dt_m_end)],
        phase=EventPhase.MONTAJE,
        db=db_super,
    )
    assert res_m is not None


def test_discontinuous_agenda_slots(db_super, tenant_a, user_a):
    space1 = Space(
        tenant_id=tenant_a.id,
        name="Space C",
        slug="space-c",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space1)
    db_super.commit()

    today = date.today()
    dt_slot1_start = datetime.combine(today, time(10, 0))
    dt_slot1_end = datetime.combine(today, time(12, 0))

    dt_slot2_start = datetime.combine(today, time(16, 0))
    dt_slot2_end = datetime.combine(today, time(18, 0))

    res = create_phased_reservation(
        tenant_id=tenant_a.id,
        user_id=user_a.id,
        space_id=space1.id,
        slots=[(dt_slot1_start, dt_slot1_end), (dt_slot2_start, dt_slot2_end)],
        phase=EventPhase.USO,
        db=db_super,
    )

    assert res.multi_day is False
    assert res.hora_inicio == time(10, 0)
    assert res.hora_fin == time(18, 0)
    assert len(res.slots) == 2
