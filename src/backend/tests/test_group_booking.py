import pytest
from datetime import date, time, timedelta
from app.modules.booking.services import create_group_reservation, SlotNotAvailableError
from app.modules.booking.models import ReservationStatus, EventPhase
from app.modules.inventory.models import Inventory, SlotStatus, Space


def test_create_group_reservation_atomic_success(db_super, tenant_a, user_a):
    space1 = Space(
        tenant_id=tenant_a.id,
        name="Space 1",
        slug="space-1",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    space2 = Space(
        tenant_id=tenant_a.id,
        name="Space 2",
        slug="space-2",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add_all([space1, space2])
    db_super.commit()

    space_ids = [space1.id, space2.id]
    dates = [date.today(), date.today() + timedelta(days=1)]
    hora_inicio = time(10, 0)
    hora_fin = time(12, 0)

    reservations = create_group_reservation(
        tenant_id=tenant_a.id,
        user_id=user_a.id,
        space_ids=space_ids,
        dates=dates,
        hora_inicio=hora_inicio,
        hora_fin=hora_fin,
        db=db_super,
    )

    assert len(reservations) == 4
    group_id = reservations[0].group_event_id
    assert group_id is not None
    assert all(r.group_event_id == group_id for r in reservations)
    assert all(r.status == ReservationStatus.SOFT_HOLD for r in reservations)
    assert all(r.multi_day is True for r in reservations)
    assert all(r.phase == EventPhase.USO for r in reservations)

    slots = (
        db_super.query(Inventory)
        .filter(Inventory.reservation_id.in_([r.id for r in reservations]))
        .all()
    )
    assert len(slots) == 4
    assert all(s.estado == SlotStatus.SOFT_HOLD for s in slots)


def test_create_group_reservation_rollback_on_conflict(db_super, tenant_a, user_a):
    space1 = Space(
        tenant_id=tenant_a.id,
        name="Space 1",
        slug="space-1-conflict",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    space2 = Space(
        tenant_id=tenant_a.id,
        name="Space 2",
        slug="space-2-conflict",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add_all([space1, space2])
    db_super.commit()

    space_ids = [space1.id, space2.id]
    dates = [date.today()]
    hora_inicio = time(10, 0)
    hora_fin = time(12, 0)

    # Pre-book space2 manually
    inv = Inventory(
        space_id=space2.id,
        tenant_id=tenant_a.id,
        fecha=dates[0],
        hora_inicio=hora_inicio,
        hora_fin=hora_fin,
        estado=SlotStatus.RESERVED,
    )
    db_super.add(inv)
    db_super.commit()

    with pytest.raises(SlotNotAvailableError):
        try:
            create_group_reservation(
                tenant_id=tenant_a.id,
                user_id=user_a.id,
                space_ids=space_ids,
                dates=dates,
                hora_inicio=hora_inicio,
                hora_fin=hora_fin,
                db=db_super,
            )
        except SlotNotAvailableError:
            db_super.rollback()
            raise

    # Parent space shouldn't be locked
    parent_inv = (
        db_super.query(Inventory)
        .filter(
            Inventory.space_id == space1.id,
            Inventory.fecha == dates[0],
            Inventory.estado == SlotStatus.SOFT_HOLD,
        )
        .first()
    )
    assert parent_inv is None


def test_soft_hold_state_transition(db_super, tenant_a, user_a):
    space1 = Space(
        tenant_id=tenant_a.id,
        name="Space 1",
        slug="space-1-soft",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space1)
    db_super.commit()

    res = create_group_reservation(
        tenant_id=tenant_a.id,
        user_id=user_a.id,
        space_ids=[space1.id],
        dates=[date.today()],
        hora_inicio=time(10, 0),
        hora_fin=time(12, 0),
        db=db_super,
    )[0]
    assert res.status == ReservationStatus.SOFT_HOLD
