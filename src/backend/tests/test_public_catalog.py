"""Tests for public catalog: GET /api/public/sedes and GET /api/spaces with tenant_id/sede (no JWT)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.inventory.models import Space


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.integration
def test_public_sedes_returns_active_tenants_without_auth(client: TestClient, tenant_a, tenant_b, db_super):
    """GET /api/public/sedes returns list of active tenants (id, name, slug) without JWT."""
    r = client.get("/api/public/sedes")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    ids = {s["id"] for s in data}
    assert str(tenant_a.id) in ids
    assert str(tenant_b.id) in ids
    for s in data:
        assert "id" in s and "name" in s and "slug" in s
        assert len(s) == 3


@pytest.mark.integration
def test_public_sedes_inactive_tenant_not_listed(client: TestClient, tenant_a, db_super):
    """GET /api/public/sedes returns only is_active=True tenants."""
    tenant_a.is_active = False
    db_super.add(tenant_a)
    db_super.commit()
    r = client.get("/api/public/sedes")
    assert r.status_code == 200
    data = r.json()
    ids = [s["id"] for s in data]
    assert str(tenant_a.id) not in ids


@pytest.mark.integration
def test_spaces_anonymous_with_tenant_id_returns_that_tenant_spaces(
    client: TestClient, tenant_a, tenant_b, db_super
):
    """GET /api/spaces?tenant_id=<id> without JWT returns spaces of that tenant only."""
    space_a = Space(
        tenant_id=tenant_a.id,
        name="Space A",
        slug="space-a-pub",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    space_b = Space(
        tenant_id=tenant_b.id,
        name="Space B",
        slug="space-b-pub",
        capacidad_maxima=5,
        precio_por_hora=50,
    )
    db_super.add(space_a)
    db_super.add(space_b)
    db_super.commit()
    r = client.get(f"/api/spaces?tenant_id={tenant_a.id}")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["slug"] == "space-a-pub"
    r2 = client.get(f"/api/spaces?tenant_id={tenant_b.id}")
    assert r2.status_code == 200
    assert len(r2.json()) == 1
    assert r2.json()[0]["slug"] == "space-b-pub"


@pytest.mark.integration
def test_spaces_anonymous_with_sede_slug_returns_that_tenant_spaces(
    client: TestClient, tenant_a, tenant_b, db_super
):
    """GET /api/spaces?sede=<slug> without JWT returns spaces of that tenant only."""
    space_a = Space(
        tenant_id=tenant_a.id,
        name="Space A2",
        slug="space-a2-pub",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    db_super.add(space_a)
    db_super.commit()
    r = client.get(f"/api/spaces?sede={tenant_a.slug}")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert any(s["slug"] == "space-a2-pub" for s in data)


@pytest.mark.integration
def test_spaces_anonymous_invalid_sede_returns_default_or_401(
    client: TestClient, tenant_a, db_super
):
    """GET /api/spaces?sede=invalid-slug may use default tenant or 401 if no default."""
    # With no DEFAULT_TENANT_ID, first tenant is used as fallback when no query match.
    # So ?sede=invalid falls back to first tenant; we just check we get 200 and a list.
    r = client.get("/api/spaces?sede=non-existent-slug-xyz")
    # Either 200 (fallback to first tenant) or 401 if no tenants
    assert r.status_code in (200, 401)
    if r.status_code == 200:
        assert isinstance(r.json(), list)


@pytest.mark.integration
def test_spaces_with_jwt_ignores_query_tenant(
    client: TestClient, tenant_a, tenant_b, token_a, db_super
):
    """With valid JWT, GET /api/spaces uses JWT tenant; query tenant_id/sede is ignored (RLS)."""
    space_a = Space(
        tenant_id=tenant_a.id,
        name="Space JWT A",
        slug="space-jwt-a",
        capacidad_maxima=10,
        precio_por_hora=100,
    )
    space_b = Space(
        tenant_id=tenant_b.id,
        name="Space JWT B",
        slug="space-jwt-b",
        capacidad_maxima=5,
        precio_por_hora=50,
    )
    db_super.add(space_a)
    db_super.add(space_b)
    db_super.commit()
    # token_a is tenant_a; requesting with ?tenant_id=tenant_b should still return only tenant_a spaces
    r = client.get(
        f"/api/spaces?tenant_id={tenant_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert all(s["slug"] != "space-jwt-b" for s in data)
    assert any(s["slug"] == "space-jwt-a" for s in data)
