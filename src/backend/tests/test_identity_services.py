"""Tests para servicios de autenticación."""

import uuid

import jwt
import pytest

from app.core.config import settings
from app.modules.identity import services
from app.modules.identity.models import User, UserRole


def test_verify_password():
    """verify_password valida correctamente."""
    hashed = services.get_password_hash("password")
    assert services.verify_password("password", hashed) is True
    assert services.verify_password("wrong", hashed) is False


def test_authenticate_user_success(db_super, tenant_a):
    """authenticate_user con credenciales válidas."""
    uid = uuid.uuid4().hex[:8]
    email = f"auth-success-{uid}@test.com"
    hashed = services.get_password_hash("password")
    u = User(
        tenant_id=tenant_a.id,
        email=email,
        hashed_password=hashed,
        full_name="Auth User",
        role=UserRole.CUSTOMER,
    )
    db_super.add(u)
    db_super.commit()
    db_super.refresh(u)
    user = services.authenticate_user(db_super, u.email, "password")
    assert user is not None
    assert user.id == u.id


def test_authenticate_user_wrong_password(db_super, tenant_a):
    """authenticate_user con password incorrecta retorna None."""
    uid = uuid.uuid4().hex[:8]
    email = f"wrong-pw-{uid}@test.com"
    hashed = services.get_password_hash("password")
    u = User(
        tenant_id=tenant_a.id,
        email=email,
        hashed_password=hashed,
        full_name="Wrong PW",
        role=UserRole.CUSTOMER,
    )
    db_super.add(u)
    db_super.commit()
    user = services.authenticate_user(db_super, u.email, "wrong")
    assert user is None


def test_authenticate_user_nonexistent_email(db_super):
    """authenticate_user con email inexistente retorna None."""
    user = services.authenticate_user(db_super, "fake@example.com", "password")
    assert user is None


def test_authenticate_user_inactive(db_super, tenant_a):
    """authenticate_user con usuario inactivo retorna None."""
    uid = uuid.uuid4().hex[:8]
    email = f"inactive-{uid}@test.com"
    hashed = services.get_password_hash("password")
    inactive = User(
        tenant_id=tenant_a.id,
        email=email,
        hashed_password=hashed,
        full_name="Inactive",
        role=UserRole.CUSTOMER,
        is_active=False,
    )
    db_super.add(inactive)
    db_super.commit()

    user = services.authenticate_user(db_super, email, "password")
    assert user is None


def test_create_access_token(user_a):
    """create_access_token genera JWT con estructura correcta."""
    token = services.create_access_token(user_a)

    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

    assert payload["tenant_id"] == str(user_a.tenant_id)
    assert payload["role"] == user_a.role.value
    assert payload["sub"] == str(user_a.id)
    assert "exp" in payload
    assert "iat" in payload


def test_get_password_hash():
    """get_password_hash produce hash que verify_password acepta."""
    hashed = services.get_password_hash("secret123")
    assert services.verify_password("secret123", hashed) is True
    assert services.verify_password("wrong", hashed) is False
