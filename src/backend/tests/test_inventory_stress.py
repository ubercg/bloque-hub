"""Stress tests: concurrent block on same slot (no overbooking)."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, time

import pytest
from fastapi.testclient import TestClient

from app.modules.inventory.models import SlotStatus


def _block_slot(
    client: TestClient,
    token: str,
    space_id: str,
    fecha: date,
    hora_inicio: time,
    hora_fin: time,
    as_parent: bool,
) -> int:
    r = client.post(
        f"/api/spaces/{space_id}/block",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "fecha": fecha.isoformat(),
            "hora_inicio": hora_inicio.strftime("%H:%M:%S"),
            "hora_fin": hora_fin.strftime("%H:%M:%S"),
            "as_parent": as_parent,
        },
    )
    return r.status_code


@pytest.mark.integration
@pytest.mark.skip(reason="Fix pendiente en TASK separada")
def test_concurrent_block_same_parent_slot(
    client: TestClient,
    token_a: str,
    tenant_a,
    db_super,
):
    """N concurrent blocks on the same parent slot: all complete, state consistent (no overbooking)."""
    from app.modules.inventory.models import Space, SpaceRelationship, RelationshipType

    parent = Space(
        tenant_id=tenant_a.id,
        name="ParentStress",
        slug="parent-stress",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    child = Space(
        tenant_id=tenant_a.id,
        name="ChildStress",
        slug="child-stress",
        capacidad_maxima=5,
        precio_por_hora=50,
    )
    db_super.add(parent)
    db_super.add(child)
    db_super.commit()
    db_super.refresh(parent)
    db_super.refresh(child)

    rel = SpaceRelationship(
        tenant_id=tenant_a.id,
        parent_space_id=parent.id,
        child_space_id=child.id,
        relationship_type=RelationshipType.PARENT_CHILD,
    )
    db_super.add(rel)
    db_super.commit()

    fecha = date(2026, 4, 1)
    hora_inicio = time(9, 0)
    hora_fin = time(10, 0)
    N = 10

    with ThreadPoolExecutor(max_workers=N) as ex:
        futures = [
            ex.submit(
                _block_slot,
                client,
                token_a,
                str(parent.id),
                fecha,
                hora_inicio,
                hora_fin,
                True,
            )
            for _ in range(N)
        ]
        codes = [f.result() for f in as_completed(futures)]

    assert all(c == 204 for c in codes), f"Expected all 204, got {codes}"

    # Final state: one slot per space, parent TTL_BLOCKED, child BLOCKED_BY_PARENT
    r_p = client.get(
        f"/api/spaces/{parent.id}/availability",
        headers={"Authorization": f"Bearer {token_a}"},
        params={"fecha_desde": fecha, "fecha_hasta": fecha},
    )
    r_c = client.get(
        f"/api/spaces/{child.id}/availability",
        headers={"Authorization": f"Bearer {token_a}"},
        params={"fecha_desde": fecha, "fecha_hasta": fecha},
    )
    assert r_p.status_code == 200 and r_c.status_code == 200
    slots_p = r_p.json()
    slots_c = r_c.json()
    assert len(slots_p) == 1 and slots_p[0]["estado"] == SlotStatus.TTL_BLOCKED.value
    assert len(slots_c) == 1 and slots_c[0]["estado"] == SlotStatus.BLOCKED_BY_PARENT.value
