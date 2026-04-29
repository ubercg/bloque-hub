"""
Integration tests: tenant isolation with RLS.
User A must not see or access User B's data (different tenant).
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_list_users_returns_only_current_tenant(
    client: TestClient,
    token_a: str,
    token_b: str,
    user_a,
    user_b,
):
    """Listing users with token A returns only users from tenant A; token B only tenant B."""
    r_a = client.get("/api/users", headers={"Authorization": f"Bearer {token_a}"})
    assert r_a.status_code == 200
    users_a = r_a.json()
    assert len(users_a) == 1
    assert users_a[0]["id"] == str(user_a.id)
    assert users_a[0]["tenant_id"] == str(user_a.tenant_id)

    r_b = client.get("/api/users", headers={"Authorization": f"Bearer {token_b}"})
    assert r_b.status_code == 200
    users_b = r_b.json()
    assert len(users_b) == 1
    assert users_b[0]["id"] == str(user_b.id)
    assert users_b[0]["tenant_id"] == str(user_b.tenant_id)


@pytest.mark.integration
def test_get_user_other_tenant_returns_404(
    client: TestClient,
    token_a: str,
    user_b,
):
    """User A cannot see user B by ID; RLS hides the row -> 404."""
    r = client.get(
        f"/api/users/{user_b.id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r.status_code == 404


@pytest.mark.integration
def test_me_returns_tenant_and_role(
    client: TestClient,
    token_a: str,
    tenant_a,
    user_a,
):
    """GET /api/me returns tenant_id and role from JWT."""
    r = client.get("/api/me", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 200
    data = r.json()
    assert data["tenant_id"] == str(tenant_a.id)
    assert data["role"] == "CUSTOMER"
    assert data["user_id"] == str(user_a.id)


@pytest.mark.integration
def test_protected_endpoint_without_token_returns_401(client: TestClient):
    """Endpoints that require tenant return 401 when no token."""
    r = client.get("/api/users")
    assert r.status_code == 401
    r = client.get("/api/me")
    assert r.status_code == 401
