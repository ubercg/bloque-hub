"""CRUD tenants (SUPERADMIN): POST, GET, PATCH; sin DELETE físico."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.modules.identity.models import Tenant


def test_create_tenant_superadmin_201(client: TestClient, token_superadmin_a: str):
    slug = f"new-tenant-{uuid.uuid4().hex[:8]}"
    r = client.post(
        "/api/tenants",
        json={"name": "Nueva sede", "slug": slug, "max_discount_threshold": 15.5},
        headers={"Authorization": f"Bearer {token_superadmin_a}"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["name"] == "Nueva sede"
    assert data["slug"] == slug
    assert data["is_active"] is True
    assert data["max_discount_threshold"] == 15.5
    assert "id" in data


def test_create_tenant_duplicate_slug_409(client: TestClient, token_superadmin_a: str, tenant_a: Tenant):
    r = client.post(
        "/api/tenants",
        json={"name": "Dup", "slug": tenant_a.slug},
        headers={"Authorization": f"Bearer {token_superadmin_a}"},
    )
    assert r.status_code == 409


def test_create_tenant_non_superadmin_403(client: TestClient, token_commercial_a: str):
    r = client.post(
        "/api/tenants",
        json={"name": "X", "slug": f"x-{uuid.uuid4().hex[:8]}"},
        headers={"Authorization": f"Bearer {token_commercial_a}"},
    )
    assert r.status_code == 403


def test_create_tenant_invalid_slug_422(client: TestClient, token_superadmin_a: str):
    r = client.post(
        "/api/tenants",
        json={"name": "Bad", "slug": "Invalid_Slug!"},
        headers={"Authorization": f"Bearer {token_superadmin_a}"},
    )
    assert r.status_code == 422


def test_get_tenant_200(client: TestClient, token_superadmin_a: str, tenant_a: Tenant):
    r = client.get(
        f"/api/tenants/{tenant_a.id}",
        headers={"Authorization": f"Bearer {token_superadmin_a}"},
    )
    assert r.status_code == 200
    assert r.json()["id"] == str(tenant_a.id)
    assert "max_discount_threshold" in r.json()


def test_patch_tenant_deactivate(client: TestClient, token_superadmin_a: str, tenant_b: Tenant):
    assert tenant_b.is_active is True
    r = client.patch(
        f"/api/tenants/{tenant_b.id}",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token_superadmin_a}"},
    )
    assert r.status_code == 200
    assert r.json()["is_active"] is False


def test_patch_tenant_slug_conflict_409(
    client: TestClient, token_superadmin_a: str, tenant_a: Tenant, tenant_b: Tenant
):
    r = client.patch(
        f"/api/tenants/{tenant_b.id}",
        json={"slug": tenant_a.slug},
        headers={"Authorization": f"Bearer {token_superadmin_a}"},
    )
    assert r.status_code == 409


def test_list_tenants_includes_max_discount(
    client: TestClient, token_superadmin_a: str, tenant_a: Tenant
):
    r = client.get(
        "/api/tenants",
        headers={"Authorization": f"Bearer {token_superadmin_a}"},
    )
    assert r.status_code == 200
    rows = r.json()
    assert any(t["id"] == str(tenant_a.id) for t in rows)
    assert all("max_discount_threshold" in t for t in rows)
