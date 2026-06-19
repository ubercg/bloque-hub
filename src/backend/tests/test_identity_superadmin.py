"""
Integration tests for Identity Superadmin (Users CRUD).
Tests must run against the real DB using the provided fixtures to guarantee RLS and transactional integrity.
"""

import uuid
import pytest
from fastapi.testclient import TestClient

from app.modules.identity.models import Tenant, User, UserRole


@pytest.mark.integration
def test_create_user_cross_tenant_success(
    client: TestClient, token_superadmin_a: str, tenant_b: Tenant
):
    """A SUPERADMIN in Tenant A can create a user in Tenant B (cross-tenant RLS bypass)."""
    new_email = f"new-cross-tenant-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/api/users",
        json={
            "tenant_id": str(tenant_b.id),
            "email": new_email,
            "password": "securepassword",
            "full_name": "Cross Tenant User",
            "role": "CUSTOMER",
        },
        headers={"Authorization": f"Bearer {token_superadmin_a}"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["email"] == new_email
    assert data["tenant_id"] == str(tenant_b.id)


@pytest.mark.integration
def test_create_user_duplicate_email_globally_fails(
    client: TestClient, token_superadmin_a: str, tenant_b: Tenant, user_a: User
):
    """Creating a user with an email that exists in another tenant fails globally."""
    r = client.post(
        "/api/users",
        json={
            "tenant_id": str(tenant_b.id),
            "email": user_a.email,  # Existing email from tenant_a
            "password": "securepassword",
            "full_name": "Duplicate Global",
            "role": "CUSTOMER",
        },
        headers={"Authorization": f"Bearer {token_superadmin_a}"},
    )
    assert r.status_code == 409, r.text
    assert "globally" in r.json()["detail"].lower()


@pytest.mark.integration
def test_update_user_move_tenant_success(
    client: TestClient, token_superadmin_a: str, tenant_b: Tenant, user_customer2_a: User
):
    """A SUPERADMIN moves a user from Tenant A to Tenant B."""
    assert str(user_customer2_a.tenant_id) != str(tenant_b.id)

    r = client.patch(
        f"/api/users/{user_customer2_a.id}",
        json={"tenant_id": str(tenant_b.id), "full_name": "Moved User"},
        headers={"Authorization": f"Bearer {token_superadmin_a}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["tenant_id"] == str(tenant_b.id)
    assert data["full_name"] == "Moved User"


@pytest.mark.integration
def test_update_user_duplicate_email_fails(
    client: TestClient, token_superadmin_a: str, user_customer2_a: User, user_b: User
):
    """Updating a user's email to one that exists in another tenant fails."""
    r = client.patch(
        f"/api/users/{user_customer2_a.id}",
        json={"email": user_b.email},
        headers={"Authorization": f"Bearer {token_superadmin_a}"},
    )
    assert r.status_code == 409, r.text
    assert "globally" in r.json()["detail"].lower()


@pytest.mark.integration
def test_update_lockout_protection_fails(
    client: TestClient, token_superadmin_a: str, user_superadmin_a: User, tenant_b: Tenant
):
    """Cannot deactivate, change role, or move the last active SUPERADMIN of a tenant."""
    # 1. Try to deactivate
    r1 = client.patch(
        f"/api/users/{user_superadmin_a.id}",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token_superadmin_a}"},
    )
    assert r1.status_code == 409
    assert "last active SUPERADMIN" in r1.json()["detail"]

    # 2. Try to change role
    r2 = client.patch(
        f"/api/users/{user_superadmin_a.id}",
        json={"role": "CUSTOMER"},
        headers={"Authorization": f"Bearer {token_superadmin_a}"},
    )
    assert r2.status_code == 409

    # 3. Try to move to another tenant
    r3 = client.patch(
        f"/api/users/{user_superadmin_a.id}",
        json={"tenant_id": str(tenant_b.id)},
        headers={"Authorization": f"Bearer {token_superadmin_a}"},
    )
    assert r3.status_code == 409


@pytest.mark.integration
def test_delete_lockout_protection_fails(
    client: TestClient, token_superadmin_a: str, user_superadmin_a: User
):
    """Cannot soft-delete the last active SUPERADMIN of a tenant."""
    r = client.delete(
        f"/api/users/{user_superadmin_a.id}",
        headers={"Authorization": f"Bearer {token_superadmin_a}"},
    )
    assert r.status_code == 409
    assert "last active SUPERADMIN" in r.json()["detail"]


@pytest.mark.integration
def test_delete_user_success(
    client: TestClient, token_superadmin_a: str, user_customer2_a: User
):
    """SUPERADMIN can successfully soft-delete a normal user."""
    assert user_customer2_a.is_active is True
    r = client.delete(
        f"/api/users/{user_customer2_a.id}",
        headers={"Authorization": f"Bearer {token_superadmin_a}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["is_active"] is False


@pytest.mark.integration
def test_commercial_forbidden_all_endpoints(
    client: TestClient, token_commercial_a: str, user_a: User, tenant_a: Tenant
):
    """A COMMERCIAL user gets 403 when trying to access admin user endpoints."""
    # POST
    r1 = client.post(
        "/api/users",
        json={
            "tenant_id": str(tenant_a.id),
            "email": f"test-{uuid.uuid4().hex[:6]}@example.com",
            "password": "securepassword",
            "full_name": "Test",
            "role": "CUSTOMER",
        },
        headers={"Authorization": f"Bearer {token_commercial_a}"},
    )
    assert r1.status_code == 403

    # PATCH
    r2 = client.patch(
        f"/api/users/{user_a.id}",
        json={"full_name": "Changed"},
        headers={"Authorization": f"Bearer {token_commercial_a}"},
    )
    assert r2.status_code == 403

    # DELETE
    r3 = client.delete(
        f"/api/users/{user_a.id}",
        headers={"Authorization": f"Bearer {token_commercial_a}"},
    )
    assert r3.status_code == 403

@pytest.mark.integration
def test_reset_password_success(
    client: TestClient, token_superadmin_a: str, user_customer2_a: User
):
    """SUPERADMIN changes password via PATCH. Check hash is hidden and login works."""
    new_password = "NewSecurePassword123!"
    
    r = client.patch(
        f"/api/users/{user_customer2_a.id}",
        json={"password": new_password},
        headers={"Authorization": f"Bearer {token_superadmin_a}"}
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "hashed_password" not in data
    assert "password" not in data
    
    # Try login with new password
    login_req_new = client.post("/api/auth/login", json={"email": user_customer2_a.email, "password": new_password})
    assert login_req_new.status_code == 200
    
    # Try login with the old password ("password")
    login_req_old = client.post("/api/auth/login", json={"email": user_customer2_a.email, "password": "password"})
    assert login_req_old.status_code == 401

@pytest.mark.integration
def test_reactivate_user_success(
    client: TestClient, token_superadmin_a: str, user_customer2_a: User
):
    """User is is_active=False; PATCH is_active=True -> 200, user can authenticate."""
    # First, deactivate the user
    r_del = client.delete(
        f"/api/users/{user_customer2_a.id}",
        headers={"Authorization": f"Bearer {token_superadmin_a}"}
    )
    assert r_del.status_code == 200
    
    # Try login -> should fail (user inactive)
    login_req1 = client.post("/api/auth/login", json={"email": user_customer2_a.email, "password": "password"})
    assert login_req1.status_code == 401

    # Reactivate the user
    r_reactivate = client.patch(
        f"/api/users/{user_customer2_a.id}",
        json={"is_active": True},
        headers={"Authorization": f"Bearer {token_superadmin_a}"}
    )
    assert r_reactivate.status_code == 200
    assert r_reactivate.json()["is_active"] is True
    
    # Try login again -> should succeed
    login_req2 = client.post("/api/auth/login", json={"email": user_customer2_a.email, "password": "password"})
    assert login_req2.status_code == 200

@pytest.mark.integration
def test_patch_and_delete_not_found(
    client: TestClient, token_superadmin_a: str
):
    """PATCH and DELETE on a non-existent user returns 404."""
    fake_id = str(uuid.uuid4())
    
    r_patch = client.patch(
        f"/api/users/{fake_id}",
        json={"full_name": "Ghost"},
        headers={"Authorization": f"Bearer {token_superadmin_a}"}
    )
    assert r_patch.status_code == 404

    r_delete = client.delete(
        f"/api/users/{fake_id}",
        headers={"Authorization": f"Bearer {token_superadmin_a}"}
    )
    assert r_delete.status_code == 404
