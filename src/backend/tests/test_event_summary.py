"""Tests for event summary merge logic and API."""

from datetime import date, time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.booking.event_summary import (
    merge_consecutive_slots,
    pick_primary_status,
)
from app.modules.booking.models import Reservation, ReservationStatus


def _slot(
    sid,
    d: date,
    hi: time,
    hf: time,
    rid=None,
    status: ReservationStatus = ReservationStatus.PENDING_SLIP,
):
    return SimpleNamespace(
        id=rid or uuid4(),
        space_id=sid,
        fecha=d,
        hora_inicio=hi,
        hora_fin=hf,
        status=status,
    )


def test_merge_single_slot():
    sid = uuid4()
    d = date(2026, 3, 27)
    rows = [_slot(sid, d, time(9, 0), time(10, 0))]
    blocks = merge_consecutive_slots(rows)
    assert len(blocks) == 1
    assert blocks[0].start == time(9, 0)
    assert blocks[0].end == time(10, 0)
    assert len(blocks[0].reservation_ids) == 1


def test_merge_three_consecutive_hours():
    sid = uuid4()
    d = date(2026, 3, 27)
    u1, u2, u3 = uuid4(), uuid4(), uuid4()
    rows = [
        _slot(sid, d, time(9, 0), time(10, 0), u1),
        _slot(sid, d, time(10, 0), time(11, 0), u2),
        _slot(sid, d, time(11, 0), time(12, 0), u3),
    ]
    blocks = merge_consecutive_slots(rows)
    assert len(blocks) == 1
    assert blocks[0].start == time(9, 0)
    assert blocks[0].end == time(12, 0)
    assert len(blocks[0].reservation_ids) == 3


def test_merge_gap_creates_two_blocks():
    sid = uuid4()
    d = date(2026, 3, 27)
    rows = [
        _slot(sid, d, time(9, 0), time(10, 0)),
        _slot(sid, d, time(11, 0), time(12, 0)),
    ]
    blocks = merge_consecutive_slots(rows)
    assert len(blocks) == 2


def test_pick_primary_all_same():
    rows = [SimpleNamespace(status=ReservationStatus.CONFIRMED)]
    st, mixed = pick_primary_status(rows)
    assert st == ReservationStatus.CONFIRMED
    assert mixed is False


def test_pick_primary_mixed():
    rows = [
        SimpleNamespace(status=ReservationStatus.CONFIRMED),
        SimpleNamespace(status=ReservationStatus.AWAITING_PAYMENT),
    ]
    st, mixed = pick_primary_status(rows)
    assert mixed is True
    assert st == ReservationStatus.AWAITING_PAYMENT


@pytest.mark.integration
def test_event_summary_endpoint_403_other_user(client, token_a: str, tenant_a, db_super):
    """Customer B cannot read event-summary for user A's reservation."""
    from app.modules.identity.models import User, UserRole

    other = User(
        tenant_id=tenant_a.id,
        email=f"other-{uuid4().hex[:8]}@test.com",
        hashed_password="x",
        full_name="Otro",
        role=UserRole.CUSTOMER,
    )
    db_super.add(other)
    db_super.commit()
    db_super.refresh(other)

    from datetime import timedelta

    from app.modules.inventory.models import Space

    suf = uuid4().hex[:8]
    sp = Space(
        tenant_id=tenant_a.id,
        name="Sala X",
        slug=f"sala-x-{suf}",
        capacidad_maxima=50,
        precio_por_hora=100,
    )
    db_super.add(sp)
    db_super.commit()
    db_super.refresh(sp)

    day = date.today() + timedelta(days=400)
    r = Reservation(
        tenant_id=tenant_a.id,
        user_id=other.id,
        space_id=sp.id,
        group_event_id=None,
        fecha=day,
        hora_inicio=time(10, 0),
        hora_fin=time(11, 0),
        status=ReservationStatus.PENDING_SLIP,
    )
    db_super.add(r)
    db_super.commit()
    db_super.refresh(r)

    res = client.get(
        f"/api/reservations/{r.id}/event-summary",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res.status_code == 403
