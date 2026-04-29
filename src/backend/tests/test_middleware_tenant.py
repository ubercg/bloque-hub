"""Tests for TenantMiddleware: JWT is decoded and tenant_id/role/user_id set on request.state."""

import uuid

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def _make_token(tenant_id: str, role: str = "CUSTOMER", sub: str | None = None) -> str:
    payload = {"tenant_id": tenant_id, "role": role}
    if sub is not None:
        payload["sub"] = sub
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def test_middleware_sets_tenant_and_role_from_valid_token():
    """With a valid Bearer token, GET /api/me returns tenant_id, role and user_id from JWT."""
    tenant_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    token = _make_token(tenant_id, "COMMERCIAL", user_id)
    client = TestClient(app)
    r = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["tenant_id"] == tenant_id
    assert data["role"] == "COMMERCIAL"
    assert data["user_id"] == user_id


def test_middleware_leaves_state_none_without_header():
    """Without Authorization header, protected endpoint returns 401."""
    client = TestClient(app)
    r = client.get("/api/me")
    assert r.status_code == 401


def test_middleware_leaves_state_none_with_invalid_token():
    """With invalid Bearer token, protected endpoint returns 401."""
    client = TestClient(app)
    r = client.get("/api/me", headers={"Authorization": "Bearer invalid-token"})
    assert r.status_code == 401
