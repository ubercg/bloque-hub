"""SUPERADMIN: crear espacio en otro tenant vía ?tenant_id= ; catálogo ?tenant_id=."""

import uuid

from fastapi.testclient import TestClient

from app.modules.identity.models import Tenant


def test_superadmin_create_space_in_other_tenant(
    client: TestClient, token_superadmin_a: str, tenant_a: Tenant, tenant_b: Tenant
):
    slug = f"sala-test-{uuid.uuid4().hex[:8]}"
    r = client.post(
        f"/api/spaces?tenant_id={tenant_b.id}",
        json={
            "name": "Sala cross-tenant",
            "slug": slug,
            "capacidad_maxima": 10,
            "precio_por_hora": 100.0,
        },
        headers={"Authorization": f"Bearer {token_superadmin_a}"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["tenant_id"] == str(tenant_b.id)
    assert data["slug"] == slug


def test_commercial_cannot_use_tenant_id_query(
    client: TestClient, token_commercial_a: str, tenant_b: Tenant
):
    slug = f"sala-denied-{uuid.uuid4().hex[:8]}"
    r = client.post(
        f"/api/spaces?tenant_id={tenant_b.id}",
        json={
            "name": "No",
            "slug": slug,
            "capacidad_maxima": 5,
            "precio_por_hora": 50.0,
        },
        headers={"Authorization": f"Bearer {token_commercial_a}"},
    )
    assert r.status_code == 403


def test_catalog_spaces_superadmin_tenant_override(
    client: TestClient, token_superadmin_a: str, tenant_b: Tenant, db_super
):
    from app.modules.inventory.models import Space

    s = Space(
        tenant_id=tenant_b.id,
        name="Listado B",
        slug=f"list-b-{uuid.uuid4().hex[:6]}",
        capacidad_maxima=5,
        precio_por_hora=1.0,
    )
    db_super.add(s)
    db_super.commit()
    db_super.refresh(s)

    r = client.get(
        f"/api/spaces?tenant_id={tenant_b.id}",
        headers={"Authorization": f"Bearer {token_superadmin_a}"},
    )
    assert r.status_code == 200
    ids = {row["id"] for row in r.json()}
    assert str(s.id) in ids
