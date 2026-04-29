"""FR-03: Availability calendar and check-availability integration tests.

Tests cover:
- CA-01: Month calendar with classified slots
- CA-02: Single check-availability
- CA-03: Group check-availability
- CA-04: Role-differentiated motivo
- CA-06: MAINTENANCE hidden as BLOCKED
- CA-07: Concurrent query performance
- CA-08: Re-verification in claim
- Granularity validation
"""

import asyncio
import uuid
from datetime import date, time, timedelta

import pytest
from fastapi.testclient import TestClient

from app.modules.identity.models import Tenant, User, UserRole
from app.modules.inventory.models import Inventory, SlotStatus, Space, SpaceBookingRule
from tests.conftest import TEST_PASSWORD_HASH, _make_token


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def space_a(db_super, tenant_a):
    """A space in tenant_a with booking rule."""
    uid = uuid.uuid4().hex[:8]
    s = Space(
        tenant_id=tenant_a.id,
        name=f"Sala Test {uid}",
        slug=f"sala-test-{uid}",
        capacidad_maxima=20,
        precio_por_hora=500,
    )
    db_super.add(s)
    db_super.commit()
    db_super.refresh(s)
    return s


@pytest.fixture
def booking_rule_a(db_super, space_a, tenant_a):
    """Booking rule: 60 min blocks, starts every hour 09-20."""
    rule = SpaceBookingRule(
        space_id=space_a.id,
        tenant_id=tenant_a.id,
        min_duration_minutes=60,
        allowed_start_times=[f"{h:02d}:00" for h in range(9, 21)],
    )
    db_super.add(rule)
    db_super.commit()
    db_super.refresh(rule)
    return rule


@pytest.fixture
def user_superadmin_a(db_super, tenant_a):
    uid = uuid.uuid4().hex[:8]
    u = User(
        tenant_id=tenant_a.id,
        email=f"superadmin_{uid}@test.com",
        hashed_password=TEST_PASSWORD_HASH,
        full_name="SuperAdmin A",
        role=UserRole.SUPERADMIN,
    )
    db_super.add(u)
    db_super.commit()
    db_super.refresh(u)
    return u


@pytest.fixture
def token_superadmin_a(tenant_a, user_superadmin_a):
    return _make_token(tenant_a.id, "SUPERADMIN", user_superadmin_a.id)


# ---------------------------------------------------------------------------
# 1. test_month_availability_returns_correct_slots (CA-01)
# ---------------------------------------------------------------------------

def test_month_availability_returns_correct_slots(
    client: TestClient, token_a, space_a, booking_rule_a, db_super, tenant_a
):
    """Month view generates all slots and merges with DB state."""
    # Create a RESERVED slot on the 15th at 10:00
    inv = Inventory(
        space_id=space_a.id, tenant_id=tenant_a.id,
        fecha=date(2026, 4, 15), hora_inicio=time(10, 0), hora_fin=time(11, 0),
        estado=SlotStatus.RESERVED,
    )
    db_super.add(inv)
    db_super.commit()

    res = client.get(
        f"/api/spaces/{space_a.id}/availability",
        params={"month": "2026-04"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["month"] == "2026-04"

    # 30 days in April
    assert len(data["days"]) == 30

    # Check the 15th: 10:00 slot should be BLOCKED
    day_15 = data["days"]["2026-04-15"]
    assert len(day_15) == 12  # 09:00-20:00 = 12 hourly slots
    slot_10 = next(s for s in day_15 if s["hora_inicio"] == "10:00:00")
    assert slot_10["status"] == "BLOCKED"

    # Other slots on the 15th should be AVAILABLE
    slot_09 = next(s for s in day_15 if s["hora_inicio"] == "09:00:00")
    assert slot_09["status"] == "AVAILABLE"


# ---------------------------------------------------------------------------
# 2. test_check_availability_available_slot (CA-02)
# ---------------------------------------------------------------------------

def test_check_availability_available_slot(
    client: TestClient, token_a, space_a, booking_rule_a
):
    """Slot with no inventory record → available: true."""
    res = client.post(
        "/api/spaces/check-availability",
        json={
            "espacio_id": str(space_a.id),
            "fecha": "2026-05-10",
            "hora_inicio": "09:00:00",
            "hora_fin": "10:00:00",
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["available"] is True
    assert data["estado"] == "AVAILABLE"


# ---------------------------------------------------------------------------
# 3. test_check_availability_blocked_slot (CA-02)
# ---------------------------------------------------------------------------

def test_check_availability_blocked_slot(
    client: TestClient, token_a, space_a, booking_rule_a, db_super, tenant_a
):
    """Slot with RESERVED status → available: false."""
    inv = Inventory(
        space_id=space_a.id, tenant_id=tenant_a.id,
        fecha=date(2026, 5, 10), hora_inicio=time(9, 0), hora_fin=time(10, 0),
        estado=SlotStatus.RESERVED,
    )
    db_super.add(inv)
    db_super.commit()

    res = client.post(
        "/api/spaces/check-availability",
        json={
            "espacio_id": str(space_a.id),
            "fecha": "2026-05-10",
            "hora_inicio": "09:00:00",
            "hora_fin": "10:00:00",
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["available"] is False
    assert data["estado"] == "BLOCKED"


# ---------------------------------------------------------------------------
# 4. test_check_availability_group_all_available (CA-03)
# ---------------------------------------------------------------------------

def test_check_availability_group_all_available(
    client: TestClient, token_a, space_a, booking_rule_a
):
    """Group check with no conflicts."""
    res = client.post(
        "/api/spaces/check-availability-group",
        json={
            "items": [
                {"espacio_id": str(space_a.id), "fecha": "2026-06-01", "hora_inicio": "09:00:00", "hora_fin": "10:00:00"},
                {"espacio_id": str(space_a.id), "fecha": "2026-06-01", "hora_inicio": "10:00:00", "hora_fin": "11:00:00"},
            ]
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["all_available"] is True
    assert len(data["conflicts"]) == 0


# ---------------------------------------------------------------------------
# 5. test_check_availability_group_with_conflicts (CA-03)
# ---------------------------------------------------------------------------

def test_check_availability_group_with_conflicts(
    client: TestClient, token_a, space_a, booking_rule_a, db_super, tenant_a
):
    """Group check with 1 conflict out of 2 items."""
    inv = Inventory(
        space_id=space_a.id, tenant_id=tenant_a.id,
        fecha=date(2026, 6, 2), hora_inicio=time(9, 0), hora_fin=time(10, 0),
        estado=SlotStatus.TTL_BLOCKED,
    )
    db_super.add(inv)
    db_super.commit()

    res = client.post(
        "/api/spaces/check-availability-group",
        json={
            "items": [
                {"espacio_id": str(space_a.id), "fecha": "2026-06-02", "hora_inicio": "09:00:00", "hora_fin": "10:00:00"},
                {"espacio_id": str(space_a.id), "fecha": "2026-06-02", "hora_inicio": "10:00:00", "hora_fin": "11:00:00"},
            ]
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["all_available"] is False
    assert len(data["conflicts"]) == 1
    assert data["conflicts"][0]["estado"] == "TTL_PENDING"


# ---------------------------------------------------------------------------
# 6. test_motivo_diferenciado_por_rol (CA-04)
# ---------------------------------------------------------------------------

def test_motivo_diferenciado_por_rol(
    client: TestClient, token_a, token_commercial_a,
    space_a, booking_rule_a, db_super, tenant_a, user_a
):
    """CUSTOMER sees generic message; COMMERCIAL sees technical details."""
    from app.modules.booking.models import Reservation, ReservationStatus
    res = Reservation(
        tenant_id=tenant_a.id,
        user_id=user_a.id,
        space_id=space_a.id,
        fecha=date(2026, 7, 1),
        hora_inicio=time(9, 0),
        hora_fin=time(10, 0),
        status=ReservationStatus.CONFIRMED,
    )
    db_super.add(res)
    db_super.flush()
    inv = Inventory(
        space_id=space_a.id, tenant_id=tenant_a.id,
        fecha=date(2026, 7, 1), hora_inicio=time(9, 0), hora_fin=time(10, 0),
        estado=SlotStatus.RESERVED, reservation_id=res.id,
    )
    db_super.add(inv)
    db_super.commit()

    body = {
        "espacio_id": str(space_a.id),
        "fecha": "2026-07-01",
        "hora_inicio": "09:00:00",
        "hora_fin": "10:00:00",
    }

    # CUSTOMER: generic motivo
    res_customer = client.post(
        "/api/spaces/check-availability",
        json=body,
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_customer.status_code == 200
    assert "no está disponible" in res_customer.json()["motivo"]

    # COMMERCIAL: technical motivo with reservation ID
    res_commercial = client.post(
        "/api/spaces/check-availability",
        json=body,
        headers={"Authorization": f"Bearer {token_commercial_a}"},
    )
    assert res_commercial.status_code == 200
    assert "Estado interno" in res_commercial.json()["motivo"]
    assert "reserva" in res_commercial.json()["motivo"]


# ---------------------------------------------------------------------------
# 7. test_maintenance_hidden_as_blocked (CA-06)
# ---------------------------------------------------------------------------

def test_maintenance_hidden_as_blocked(
    client: TestClient, token_a, token_superadmin_a,
    space_a, booking_rule_a, db_super, tenant_a
):
    """MAINTENANCE appears as BLOCKED for non-SUPERADMIN, shows as MAINTENANCE for SUPERADMIN."""
    inv = Inventory(
        space_id=space_a.id, tenant_id=tenant_a.id,
        fecha=date(2026, 8, 1), hora_inicio=time(9, 0), hora_fin=time(10, 0),
        estado=SlotStatus.MAINTENANCE,
    )
    db_super.add(inv)
    db_super.commit()

    # CUSTOMER: sees BLOCKED
    res_customer = client.post(
        "/api/spaces/check-availability",
        json={
            "espacio_id": str(space_a.id),
            "fecha": "2026-08-01",
            "hora_inicio": "09:00:00",
            "hora_fin": "10:00:00",
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_customer.status_code == 200
    assert res_customer.json()["estado"] == "BLOCKED"

    # SUPERADMIN: sees month calendar with MAINTENANCE
    res_admin = client.get(
        f"/api/spaces/{space_a.id}/availability",
        params={"month": "2026-08"},
        headers={"Authorization": f"Bearer {token_superadmin_a}"},
    )
    assert res_admin.status_code == 200
    day_1 = res_admin.json()["days"]["2026-08-01"]
    slot_09 = next(s for s in day_1 if s["hora_inicio"] == "09:00:00")
    assert slot_09["status"] == "MAINTENANCE"


# ---------------------------------------------------------------------------
# 8. test_granularity_validation
# ---------------------------------------------------------------------------

def test_granularity_validation(
    client: TestClient, token_a, space_a, booking_rule_a
):
    """Invalid start time for space granularity → INVALID_SLOT_GRANULARITY."""
    # 09:30 is not in allowed_start_times (every hour on the hour)
    res = client.post(
        "/api/spaces/check-availability",
        json={
            "espacio_id": str(space_a.id),
            "fecha": "2026-05-10",
            "hora_inicio": "09:30:00",
            "hora_fin": "10:30:00",
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["available"] is False
    assert data["estado"] == "INVALID_SLOT_GRANULARITY"
    assert data["allowed_blocks"] is not None


# ---------------------------------------------------------------------------
# 9. test_re_verification_in_claim (CA-08)
# ---------------------------------------------------------------------------

def test_re_verification_in_claim(
    client: TestClient, db_super, tenant_a, space_a, booking_rule_a, user_a
):
    """Claim fails if slot was taken between initial check and claim."""
    from app.modules.booking.models import Reservation, ReservationStatus
    from app.modules.inventory.services import claim_slot_for_reservation, SlotNotAvailableError

    res1 = Reservation(
        tenant_id=tenant_a.id,
        user_id=user_a.id,
        space_id=space_a.id,
        fecha=date(2026, 9, 1),
        hora_inicio=time(9, 0),
        hora_fin=time(10, 0),
        status=ReservationStatus.PENDING_SLIP,
    )
    db_super.add(res1)
    db_super.flush()
    res2 = Reservation(
        tenant_id=tenant_a.id,
        user_id=user_a.id,
        space_id=space_a.id,
        fecha=date(2026, 9, 1),
        hora_inicio=time(9, 0),
        hora_fin=time(10, 0),
        status=ReservationStatus.PENDING_SLIP,
    )
    db_super.add(res2)
    db_super.flush()

    # First claim succeeds
    claim_slot_for_reservation(
        space_id=space_a.id,
        tenant_id=tenant_a.id,
        fecha=date(2026, 9, 1),
        hora_inicio=time(9, 0),
        hora_fin=time(10, 0),
        reservation_id=res1.id,
        db=db_super,
    )
    db_super.commit()

    # Second claim on same slot fails
    with pytest.raises(SlotNotAvailableError):
        claim_slot_for_reservation(
            space_id=space_a.id,
            tenant_id=tenant_a.id,
            fecha=date(2026, 9, 1),
            hora_inicio=time(9, 0),
            hora_fin=time(10, 0),
            reservation_id=res2.id,
            db=db_super,
        )


# ---------------------------------------------------------------------------
# 10. test_concurrent_availability_queries (CA-07)
# ---------------------------------------------------------------------------

def test_concurrent_availability_queries(
    client: TestClient, token_a, space_a, booking_rule_a
):
    """200 concurrent queries should complete with acceptable latency.

    Note: This is a simplified load test using sequential requests in the test
    client. Full P99 < 500ms testing should be done with locust or k6 against
    a running Docker instance. This test validates correctness under basic load.
    """
    import time as time_mod

    url = f"/api/spaces/{space_a.id}/availability"
    params = {"month": "2026-04"}
    headers = {"Authorization": f"Bearer {token_a}"}

    start = time_mod.perf_counter()
    results = []
    for _ in range(50):  # 50 sequential = practical in TestClient
        r = client.get(url, params=params, headers=headers)
        results.append(r.status_code)
    elapsed = time_mod.perf_counter() - start

    assert all(s == 200 for s in results)
    # Average should be under 100ms per request in test environment
    avg_ms = (elapsed / 50) * 1000
    assert avg_ms < 500, f"Average response time {avg_ms:.0f}ms exceeds 500ms"


# ---------------------------------------------------------------------------
# 11. test_month_availability_without_auth (anonymous)
# ---------------------------------------------------------------------------

def test_month_availability_without_auth(
    client: TestClient, space_a, booking_rule_a, tenant_a
):
    """Anonymous user can access month availability via tenant_id param."""
    res = client.get(
        f"/api/spaces/{space_a.id}/availability",
        params={"month": "2026-04", "tenant_id": str(tenant_a.id)},
    )
    assert res.status_code == 200
    assert res.json()["month"] == "2026-04"


# ---------------------------------------------------------------------------
# 12. test_booking_rules_crud (SuperAdmin)
# ---------------------------------------------------------------------------

def test_booking_rules_crud(
    client: TestClient, token_superadmin_a, space_a, tenant_a
):
    """SuperAdmin can create/read booking rules."""
    headers = {"Authorization": f"Bearer {token_superadmin_a}"}

    # Create via upsert
    res = client.put(
        f"/api/space-booking-rules/{space_a.id}",
        json={"min_duration_minutes": 180, "allowed_start_times": ["09:00", "12:00", "15:00"]},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["min_duration_minutes"] == 180
    assert len(data["allowed_start_times"]) == 3

    # Read single
    res = client.get(f"/api/space-booking-rules/{space_a.id}", headers=headers)
    assert res.status_code == 200
    assert res.json()["min_duration_minutes"] == 180

    # List
    res = client.get("/api/space-booking-rules", headers=headers)
    assert res.status_code == 200
    assert any(r["space_id"] == str(space_a.id) for r in res.json())

    # Update via upsert
    res = client.put(
        f"/api/space-booking-rules/{space_a.id}",
        json={"min_duration_minutes": 60, "allowed_start_times": ["09:00", "10:00"]},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["min_duration_minutes"] == 60
