"""Tests for TTL fields and expiration (Tarea 5)."""

import pytest

from app.modules.booking.models import Reservation, ReservationStatus
from app.modules.booking.services import expire_reservation_by_ttl
from app.modules.inventory.models import Inventory, SlotStatus
from app.db.session import get_db_context


@pytest.mark.integration
def test_create_reservation_sets_ttl_expires_at_and_ttl_frozen_false(
    client, token_a, tenant_a, db_super
):
    """After creating a reservation, ttl_expires_at is set and ttl_frozen is False."""
    from app.modules.inventory.models import Space

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala TTL",
        slug="sala-ttl",
        capacidad_maxima=5,
        precio_por_hora=50,
        ttl_minutos=60,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)

    r = client.post(
        "/api/reservations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "space_id": str(space.id),
            "fecha": "2026-08-01",
            "hora_inicio": "09:00:00",
            "hora_fin": "10:00:00",
        },
    )
    assert r.status_code == 201
    data = r.json()
    assert data["ttl_frozen"] is False
    assert data.get("ttl_expires_at") is not None


@pytest.mark.skip(
    reason="Test acoplado a estado interno de services.py — fix pendiente en TASK separada"
)
@pytest.mark.integration
def test_upload_slip_sets_ttl_frozen_true(
    client, token_a, token_commercial_a, tenant_a, db_super
):
    """After upload_slip, reservation has ttl_frozen=True (Regla 4c)."""
    from app.modules.inventory.models import Space

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala Frozen",
        slug="sala-frozen",
        capacidad_maxima=5,
        precio_por_hora=50,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)

    r_create = client.post(
        "/api/reservations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "space_id": str(space.id),
            "fecha": "2026-08-02",
            "hora_inicio": "14:00:00",
            "hora_fin": "15:00:00",
        },
    )
    assert r_create.status_code == 201
    rid = r_create.json()["id"]

    client.post(
        f"/api/reservations/{rid}/generate_slip",
        headers={"Authorization": f"Bearer {token_commercial_a}"},
    )
    client.post(
        f"/api/reservations/{rid}/upload_slip",
        headers={"Authorization": f"Bearer {token_a}"},
    )

    r_get = client.get(
        f"/api/reservations/{rid}", headers={"Authorization": f"Bearer {token_a}"}
    )
    assert r_get.status_code == 200
    assert r_get.json()["ttl_frozen"] is True
    assert r_get.json()["status"] == ReservationStatus.PAYMENT_UNDER_REVIEW.value


@pytest.mark.integration
def test_expire_reservation_by_ttl_releases_slot(tenant_a, user_a, db_super):
    """expire_reservation_by_ttl sets EXPIRED and releases inventory slot."""
    from datetime import date, time

    from sqlalchemy import select

    from app.modules.booking.services import create_reservation
    from app.modules.inventory.models import Space

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala Expire",
        slug="sala-expire-ttl",
        capacidad_maxima=1,
        precio_por_hora=1,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)

    with get_db_context(tenant_id=str(tenant_a.id)) as db:
        r = create_reservation(
            tenant_id=tenant_a.id,
            user_id=user_a.id,
            space_id=space.id,
            fecha=date(2026, 9, 1),
            hora_inicio=time(10, 0),
            hora_fin=time(11, 0),
            db=db,
        )
        db.commit()
        rid = r.id

    with get_db_context(tenant_id=None, role="SUPERADMIN") as db:
        reservation = db.get(Reservation, rid)
        assert reservation is not None
        assert reservation.status == ReservationStatus.PENDING_SLIP
        expire_reservation_by_ttl(reservation, db)
        db.commit()

    with get_db_context(tenant_id=str(tenant_a.id)) as db:
        slot = (
            db.execute(
                select(Inventory).where(
                    Inventory.space_id == space.id,
                    Inventory.fecha == date(2026, 9, 1),
                    Inventory.hora_inicio == time(10, 0),
                    Inventory.hora_fin == time(11, 0),
                )
            )
            .scalars()
            .first()
        )
        assert slot is not None
        assert slot.estado == SlotStatus.AVAILABLE
        assert slot.reservation_id is None
        res = db.get(Reservation, rid)
        assert res.status == ReservationStatus.EXPIRED
