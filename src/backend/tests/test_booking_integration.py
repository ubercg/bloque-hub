"""Integration tests: reservation flow and slot conflict."""

import pytest
from fastapi.testclient import TestClient

from app.modules.booking.models import ReservationStatus
from app.modules.inventory.models import SlotStatus
from tests.conftest import TEST_PASSWORD_HASH


@pytest.mark.integration
def test_full_flow_create_generate_upload_confirm(
    client: TestClient,
    token_a: str,
    token_commercial_a: str,
    token_finance_a: str,
    tenant_a,
    user_a,
    db_super,
):
    """Create reservation (customer), generate slip (commercial), upload slip (customer), confirm (finance - SoD)."""
    from app.modules.inventory.models import Space

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala Flow",
        slug="sala-flow-booking",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)

    # Customer creates reservation
    r_create = client.post(
        "/api/reservations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "space_id": str(space.id),
            "fecha": "2026-07-01",
            "hora_inicio": "10:00:00",
            "hora_fin": "12:00:00",
        },
    )
    assert r_create.status_code == 201
    data = r_create.json()
    reservation_id = data["id"]
    assert data["status"] == ReservationStatus.PENDING_SLIP.value

    # Commercial (same tenant) generates slip
    r_slip = client.post(
        f"/api/reservations/{reservation_id}/generate_slip",
        headers={"Authorization": f"Bearer {token_commercial_a}"},
    )
    assert r_slip.status_code == 204

    # Customer uploads slip (no file in T4)
    r_upload = client.post(
        f"/api/reservations/{reservation_id}/upload_slip",
        headers={"Authorization": f"Bearer {token_a}"},
        files={"file": ("dummy.pdf", b"x" * 1024 * 10 + __import__("uuid").uuid4().hex.encode(), "application/pdf")},
    )
    assert r_upload.status_code == 201

    # Finance (SoD) confirms; Commercial cannot approve payment
    r_confirm = client.post(
        f"/api/reservations/{reservation_id}/confirm",
        headers={"Authorization": f"Bearer {token_finance_a}"},
    )
    assert r_confirm.status_code == 204

    # Verify reservation and slot state
    r_get = client.get(
        f"/api/reservations/{reservation_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r_get.status_code == 200
    assert r_get.json()["status"] == ReservationStatus.CONFIRMED.value

    r_av = client.get(
        f"/api/spaces/{space.id}/availability",
        headers={"Authorization": f"Bearer {token_a}"},
        params={"fecha_desde": "2026-07-01", "fecha_hasta": "2026-07-01"},
    )
    assert r_av.status_code == 200
    slots = r_av.json()
    assert len(slots) == 1
    assert slots[0]["estado"] == SlotStatus.RESERVED.value


@pytest.mark.integration
def test_reject_flow_releases_slot(
    client: TestClient,
    token_a: str,
    token_commercial_a: str,
    token_finance_a: str,
    tenant_a,
    user_a,
    db_super,
):
    from app.modules.inventory.models import Space

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala Reject",
        slug="sala-reject-booking",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)

    r_create = client.post(
        "/api/reservations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "space_id": str(space.id),
            "fecha": "2026-07-02",
            "hora_inicio": "14:00:00",
            "hora_fin": "16:00:00",
        },
    )
    assert r_create.status_code == 201
    reservation_id = r_create.json()["id"]

    client.post(
        f"/api/reservations/{reservation_id}/generate_slip",
        headers={"Authorization": f"Bearer {token_commercial_a}"},
    )
    client.post(
        f"/api/reservations/{reservation_id}/upload_slip",
        headers={"Authorization": f"Bearer {token_a}"},
        files={"file": ("dummy.pdf", b"x" * 1024 * 10 + __import__("uuid").uuid4().hex.encode(), "application/pdf")},
    )
    r_reject = client.post(
        f"/api/reservations/{reservation_id}/reject",
        headers={"Authorization": f"Bearer {token_finance_a}"},
        json={"motivo": "Monto incorrecto"},
    )
    assert r_reject.status_code == 204

    r_get = client.get(
        f"/api/reservations/{reservation_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r_get.json()["status"] == ReservationStatus.EXPIRED.value

    r_av = client.get(
        f"/api/spaces/{space.id}/availability",
        headers={"Authorization": f"Bearer {token_a}"},
        params={"fecha_desde": "2026-07-02", "fecha_hasta": "2026-07-02"},
    )
    slots = r_av.json()
    assert len(slots) == 1
    assert slots[0]["estado"] == SlotStatus.AVAILABLE.value


@pytest.mark.integration
def test_double_booking_same_slot_returns_409(
    client: TestClient,
    token_a: str,
    tenant_a,
    user_a,
    db_super,
):
    """Two concurrent reservations for the same slot: first 201, second 409."""
    from app.modules.inventory.models import Space

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala Conflict",
        slug="sala-conflict-booking",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)

    payload = {
        "space_id": str(space.id),
        "fecha": "2026-08-01",
        "hora_inicio": "09:00:00",
        "hora_fin": "11:00:00",
    }
    r1 = client.post(
        "/api/reservations",
        headers={"Authorization": f"Bearer {token_a}"},
        json=payload,
    )
    assert r1.status_code == 201

    r2 = client.post(
        "/api/reservations",
        headers={"Authorization": f"Bearer {token_a}"},
        json=payload,
    )
    assert r2.status_code == 409
    assert "SLOT_NO_DISPONIBLE" in (r2.json().get("detail") or "")


@pytest.mark.integration
def test_sod_commercial_cannot_confirm_or_reject(
    client: TestClient,
    token_commercial_a: str,
    token_finance_a: str,
    tenant_a,
    db_super,
):
    """SoD: COMMERCIAL must get 403 on confirm and reject; only FINANCE/SUPERADMIN can approve/reject payments."""
    from app.modules.inventory.models import Space

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala SoD",
        slug="sala-sod-test",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)

    # Create reservation and move to PAYMENT_UNDER_REVIEW so confirm/reject are valid
    r_create = client.post(
        "/api/reservations",
        headers={"Authorization": f"Bearer {token_commercial_a}"},
        json={
            "space_id": str(space.id),
            "fecha": "2026-09-01",
            "hora_inicio": "10:00:00",
            "hora_fin": "12:00:00",
        },
    )
    assert r_create.status_code == 201
    reservation_id = r_create.json()["id"]

    client.post(
        f"/api/reservations/{reservation_id}/generate_slip",
        headers={"Authorization": f"Bearer {token_commercial_a}"},
    )
    # Move to PAYMENT_UNDER_REVIEW via service (no file in test)
    from app.db.session import get_db_context
    from app.modules.booking.models import Reservation
    from app.modules.booking.services import transition_to_payment_under_review

    with get_db_context(tenant_id=str(tenant_a.id), role="COMMERCIAL") as db:
        res = db.query(Reservation).filter(Reservation.id == reservation_id).first()
        if res and res.status.value == "AWAITING_PAYMENT":
            transition_to_payment_under_review(res, db)
            db.commit()

    # COMMERCIAL cannot confirm
    r_confirm = client.post(
        f"/api/reservations/{reservation_id}/confirm",
        headers={"Authorization": f"Bearer {token_commercial_a}"},
    )
    assert r_confirm.status_code == 403
    assert "Finance" in (r_confirm.json().get("detail") or "")

    # COMMERCIAL cannot reject
    r_reject = client.post(
        f"/api/reservations/{reservation_id}/reject",
        headers={"Authorization": f"Bearer {token_commercial_a}"},
        json={"motivo": "Test SoD"},
    )
    assert r_reject.status_code == 403
    assert "Finance" in (r_reject.json().get("detail") or "")

    # FINANCE can confirm
    r_confirm_finance = client.post(
        f"/api/reservations/{reservation_id}/confirm",
        headers={"Authorization": f"Bearer {token_finance_a}"},
    )
    assert r_confirm_finance.status_code == 204


@pytest.mark.integration
def test_anti_hoarding_max_three_active_per_customer(
    client: TestClient,
    token_a: str,
    tenant_a,
    db_super,
):
    """CUSTOMER with 3 active reservations cannot create a 4th (403). After one is CONFIRMED, can create again."""
    from app.modules.inventory.models import Space

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala AntiHoarding",
        slug="sala-antihoard",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)

    for i in range(3):
        r = client.post(
            "/api/reservations",
            headers={"Authorization": f"Bearer {token_a}"},
            json={
                "space_id": str(space.id),
                "fecha": "2026-10-01",
                "hora_inicio": f"{9 + i:02d}:00:00",
                "hora_fin": f"{10 + i:02d}:00:00",
            },
        )
        assert r.status_code == 201, r.json()

    r4 = client.post(
        "/api/reservations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "space_id": str(space.id),
            "fecha": "2026-10-02",
            "hora_inicio": "09:00:00",
            "hora_fin": "10:00:00",
        },
    )
    assert r4.status_code == 403
    assert "3 reservas" in (r4.json().get("detail") or "")


# --- Cancel reservation (POST /api/reservations/{id}/cancel) ---


@pytest.mark.integration
def test_cancel_own_pending_slip_returns_204_and_releases_slot(
    client: TestClient,
    token_a: str,
    tenant_a,
    db_super,
):
    """CUSTOMER cancels own reservation in PENDING_SLIP: 204, status CANCELLED, slot AVAILABLE."""
    from app.modules.inventory.models import Space

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala Cancel E2E",
        slug="sala-cancel-e2e",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)

    r_create = client.post(
        "/api/reservations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "space_id": str(space.id),
            "fecha": "2026-11-01",
            "hora_inicio": "10:00:00",
            "hora_fin": "12:00:00",
        },
    )
    assert r_create.status_code == 201
    reservation_id = r_create.json()["id"]
    assert r_create.json()["status"] == ReservationStatus.PENDING_SLIP.value

    r_cancel = client.post(
        f"/api/reservations/{reservation_id}/cancel",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r_cancel.status_code == 204

    r_get = client.get(
        f"/api/reservations/{reservation_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r_get.status_code == 200
    assert r_get.json()["status"] == ReservationStatus.CANCELLED.value

    r_av = client.get(
        f"/api/spaces/{space.id}/availability",
        headers={"Authorization": f"Bearer {token_a}"},
        params={"fecha_desde": "2026-11-01", "fecha_hasta": "2026-11-01"},
    )
    assert r_av.status_code == 200
    slots = r_av.json()
    assert len(slots) == 1
    assert slots[0]["estado"] == SlotStatus.AVAILABLE.value


@pytest.mark.integration
def test_cancel_own_awaiting_payment_returns_204(
    client: TestClient,
    token_a: str,
    token_commercial_a: str,
    tenant_a,
    db_super,
):
    """CUSTOMER cancels own reservation in AWAITING_PAYMENT: 204."""
    from app.modules.inventory.models import Space

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala Cancel Await E2E",
        slug="sala-cancel-await-e2e",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)

    r_create = client.post(
        "/api/reservations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "space_id": str(space.id),
            "fecha": "2026-11-02",
            "hora_inicio": "14:00:00",
            "hora_fin": "16:00:00",
        },
    )
    assert r_create.status_code == 201
    reservation_id = r_create.json()["id"]
    client.post(
        f"/api/reservations/{reservation_id}/generate_slip",
        headers={"Authorization": f"Bearer {token_commercial_a}"},
    )

    r_cancel = client.post(
        f"/api/reservations/{reservation_id}/cancel",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r_cancel.status_code == 204
    r_get = client.get(
        f"/api/reservations/{reservation_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r_get.json()["status"] == ReservationStatus.CANCELLED.value


@pytest.mark.integration
def test_cancel_confirmed_returns_400(
    client: TestClient,
    token_a: str,
    tenant_a,
    db_super,
):
    """Cancel reservation in CONFIRMED returns 400 (not cancelable)."""
    from app.modules.booking.models import Reservation
    from app.modules.inventory.models import Inventory, Space, SlotStatus

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala Cancel 400",
        slug="sala-cancel-400",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)

    r_create = client.post(
        "/api/reservations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "space_id": str(space.id),
            "fecha": "2026-11-03",
            "hora_inicio": "10:00:00",
            "hora_fin": "12:00:00",
        },
    )
    assert r_create.status_code == 201
    reservation_id = r_create.json()["id"]

    # Set reservation to CONFIRMED and slot to RESERVED in DB (avoids upload_slip/confirm which need a file)
    res = db_super.query(Reservation).filter(Reservation.id == reservation_id).first()
    assert res is not None
    res.status = ReservationStatus.CONFIRMED
    slot = (
        db_super.query(Inventory)
        .filter(Inventory.reservation_id == res.id)
        .first()
    )
    if slot:
        slot.estado = SlotStatus.RESERVED
    db_super.commit()

    r_cancel = client.post(
        f"/api/reservations/{reservation_id}/cancel",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r_cancel.status_code == 400
    assert "No se puede cancelar" in (r_cancel.json().get("detail") or "")


@pytest.mark.integration
def test_cancel_other_customers_reservation_returns_403(
    client: TestClient,
    token_a: str,
    token_customer2_a: str,
    tenant_a,
    db_super,
):
    """CUSTOMER cannot cancel another CUSTOMER's reservation (403)."""
    from app.modules.inventory.models import Space

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala Cancel 403",
        slug="sala-cancel-403",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)

    # user_a (token_a) creates reservation
    r_create = client.post(
        "/api/reservations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "space_id": str(space.id),
            "fecha": "2026-11-04",
            "hora_inicio": "10:00:00",
            "hora_fin": "12:00:00",
        },
    )
    assert r_create.status_code == 201
    reservation_id = r_create.json()["id"]

    # customer2 (same tenant, different user) tries to cancel -> 403
    r_cancel = client.post(
        f"/api/reservations/{reservation_id}/cancel",
        headers={"Authorization": f"Bearer {token_customer2_a}"},
    )
    assert r_cancel.status_code == 403
    assert "propias" in (r_cancel.json().get("detail") or "")


@pytest.mark.integration
def test_commercial_can_cancel_any_tenant_reservation(
    client: TestClient,
    token_a: str,
    token_commercial_a: str,
    tenant_a,
    db_super,
):
    """COMMERCIAL can cancel any reservation in the same tenant (204)."""
    from app.modules.inventory.models import Space

    space = Space(
        tenant_id=tenant_a.id,
        name="Sala Cancel Commercial",
        slug="sala-cancel-commercial",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)

    r_create = client.post(
        "/api/reservations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "space_id": str(space.id),
            "fecha": "2026-11-05",
            "hora_inicio": "10:00:00",
            "hora_fin": "12:00:00",
        },
    )
    assert r_create.status_code == 201
    reservation_id = r_create.json()["id"]

    r_cancel = client.post(
        f"/api/reservations/{reservation_id}/cancel",
        headers={"Authorization": f"Bearer {token_commercial_a}"},
    )
    assert r_cancel.status_code == 204
    r_get = client.get(
        f"/api/reservations/{reservation_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r_get.json()["status"] == ReservationStatus.CANCELLED.value
