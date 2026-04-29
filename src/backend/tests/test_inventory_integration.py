"""Integration tests: CRUD spaces/relationships and hierarchical block."""

from datetime import date, time

import pytest
from fastapi.testclient import TestClient

from app.modules.inventory.models import SlotStatus


@pytest.mark.integration
def test_create_relationship_cycle_returns_400(
    client: TestClient,
    token_a: str,
    tenant_a,
    db_super,
):
    """Creating a relationship that would create a cycle returns 400."""
    from app.modules.inventory.models import Space, SpaceRelationship, RelationshipType

    space_a = Space(
        tenant_id=tenant_a.id,
        name="Parent",
        slug="parent-cycle",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    space_b = Space(
        tenant_id=tenant_a.id,
        name="Child",
        slug="child-cycle",
        capacidad_maxima=5,
        precio_por_hora=50,
    )
    db_super.add(space_a)
    db_super.add(space_b)
    db_super.commit()
    db_super.refresh(space_a)
    db_super.refresh(space_b)

    rel = SpaceRelationship(
        tenant_id=tenant_a.id,
        parent_space_id=space_a.id,
        child_space_id=space_b.id,
        relationship_type=RelationshipType.PARENT_CHILD,
    )
    db_super.add(rel)
    db_super.commit()

    # Adding B→A would create cycle
    r = client.post(
        "/api/space-relationships",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "parent_space_id": str(space_b.id),
            "child_space_id": str(space_a.id),
        },
    )
    assert r.status_code == 400
    assert "circular" in r.json().get("detail", "").lower()


@pytest.mark.integration
def test_block_parent_and_children(
    client: TestClient,
    token_a: str,
    tenant_a,
    db_super,
):
    """Block parent slot: parent becomes TTL_BLOCKED, children BLOCKED_BY_PARENT."""
    from app.modules.inventory.models import Space, SpaceRelationship, RelationshipType

    parent = Space(
        tenant_id=tenant_a.id,
        name="Parent",
        slug="parent-block",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    child = Space(
        tenant_id=tenant_a.id,
        name="Child",
        slug="child-block",
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

    fecha = date(2026, 3, 1)
    hora_inicio = time(10, 0)
    hora_fin = time(12, 0)

    r = client.post(
        f"/api/spaces/{parent.id}/block",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "fecha": fecha.isoformat(),
            "hora_inicio": hora_inicio.strftime("%H:%M:%S"),
            "hora_fin": hora_fin.strftime("%H:%M:%S"),
            "as_parent": True,
        },
    )
    assert r.status_code == 204

    # Parent availability: one slot TTL_BLOCKED
    r_av = client.get(
        f"/api/spaces/{parent.id}/availability",
        headers={"Authorization": f"Bearer {token_a}"},
        params={"fecha_desde": fecha, "fecha_hasta": fecha},
    )
    assert r_av.status_code == 200
    slots_parent = r_av.json()
    assert len(slots_parent) == 1
    assert slots_parent[0]["estado"] == SlotStatus.TTL_BLOCKED.value

    # Child availability: one slot BLOCKED_BY_PARENT
    r_av_c = client.get(
        f"/api/spaces/{child.id}/availability",
        headers={"Authorization": f"Bearer {token_a}"},
        params={"fecha_desde": fecha, "fecha_hasta": fecha},
    )
    assert r_av_c.status_code == 200
    slots_child = r_av_c.json()
    assert len(slots_child) == 1
    assert slots_child[0]["estado"] == SlotStatus.BLOCKED_BY_PARENT.value


@pytest.mark.integration
def test_block_child_and_parent(
    client: TestClient,
    token_a: str,
    tenant_a,
    db_super,
):
    """Block child slot: child becomes TTL_BLOCKED, parent BLOCKED_BY_CHILD."""
    from app.modules.inventory.models import Space, SpaceRelationship, RelationshipType

    parent = Space(
        tenant_id=tenant_a.id,
        name="Parent2",
        slug="parent-block2",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    child = Space(
        tenant_id=tenant_a.id,
        name="Child2",
        slug="child-block2",
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

    fecha = date(2026, 3, 2)
    hora_inicio = time(14, 0)
    hora_fin = time(16, 0)

    r = client.post(
        f"/api/spaces/{child.id}/block",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "fecha": fecha.isoformat(),
            "hora_inicio": hora_inicio.strftime("%H:%M:%S"),
            "hora_fin": hora_fin.strftime("%H:%M:%S"),
            "as_parent": False,
        },
    )
    assert r.status_code == 204

    r_av_c = client.get(
        f"/api/spaces/{child.id}/availability",
        headers={"Authorization": f"Bearer {token_a}"},
        params={"fecha_desde": fecha, "fecha_hasta": fecha},
    )
    assert r_av_c.status_code == 200
    assert r_av_c.json()[0]["estado"] == SlotStatus.TTL_BLOCKED.value

    r_av_p = client.get(
        f"/api/spaces/{parent.id}/availability",
        headers={"Authorization": f"Bearer {token_a}"},
        params={"fecha_desde": fecha, "fecha_hasta": fecha},
    )
    assert r_av_p.status_code == 200
    assert r_av_p.json()[0]["estado"] == SlotStatus.BLOCKED_BY_CHILD.value
