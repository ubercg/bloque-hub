import os
import uuid
from urllib.parse import urlparse, urlunparse

# Use non-superuser (bloque_app) for DB so RLS applies; superuser bypasses RLS in PostgreSQL
_db_url = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/bloque_hub").strip()
if _db_url.startswith("postgresql://") or _db_url.startswith("postgres://"):
    _p = urlparse(_db_url)
    _netloc = f"bloque_app:bloque_app_secret@{_p.hostname or 'localhost'}:{_p.port or 5432}"
    os.environ["DATABASE_URL"] = urlunparse(_p._replace(netloc=_netloc))

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
import alembic.config
import alembic.command
try:
    alembic_cfg = alembic.config.Config("alembic.ini")
    alembic.command.upgrade(alembic_cfg, "head")
except Exception as e:
    print(f"Alembic upgrade failed: {e}")

from app.db.session import get_db_context
from app.main import app
from app.modules.identity.models import Tenant, User, UserRole

# Fixed bcrypt hash for "password" (no passlib runtime in tests to avoid bcrypt backend issues)
TEST_PASSWORD_HASH = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.VXg7H8nJ.9KQOu"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db_super() -> Session:
    """Session with role=SUPERADMIN for seeding data (bypasses RLS)."""
    with get_db_context(tenant_id=None, role="SUPERADMIN") as db:
        yield db


@pytest.fixture
def tenant_a(db_super: Session) -> Tenant:
    uid = uuid.uuid4().hex[:8]
    t = Tenant(name="Tenant A", slug=f"tenant-a-{uid}")
    db_super.add(t)
    db_super.commit()
    db_super.refresh(t)
    return t


@pytest.fixture
def tenant_b(db_super: Session) -> Tenant:
    uid = uuid.uuid4().hex[:8]
    t = Tenant(name="Tenant B", slug=f"tenant-b-{uid}")
    db_super.add(t)
    db_super.commit()
    db_super.refresh(t)
    return t


@pytest.fixture
def user_a(db_super: Session, tenant_a: Tenant) -> User:
    uid = uuid.uuid4().hex[:8]
    u = User(
        tenant_id=tenant_a.id,
        email=f"user_a_{uid}@tenant-a.test",
        hashed_password=TEST_PASSWORD_HASH,
        full_name="User A",
        role=UserRole.CUSTOMER,
    )
    db_super.add(u)
    db_super.commit()
    db_super.refresh(u)
    return u


@pytest.fixture
def user_b(db_super: Session, tenant_b: Tenant) -> User:
    uid = uuid.uuid4().hex[:8]
    u = User(
        tenant_id=tenant_b.id,
        email=f"user_b_{uid}@tenant-b.test",
        hashed_password=TEST_PASSWORD_HASH,
        full_name="User B",
        role=UserRole.COMMERCIAL,
    )
    db_super.add(u)
    db_super.commit()
    db_super.refresh(u)
    return u


@pytest.fixture
def user_commercial_a(db_super: Session, tenant_a: Tenant) -> User:
    """Commercial user in tenant_a for generate_slip/confirm (same tenant as customer)."""
    uid = uuid.uuid4().hex[:8]
    u = User(
        tenant_id=tenant_a.id,
        email=f"commercial_a_{uid}@tenant-a.test",
        hashed_password=TEST_PASSWORD_HASH,
        full_name="Commercial A",
        role=UserRole.COMMERCIAL,
    )
    db_super.add(u)
    db_super.commit()
    db_super.refresh(u)
    return u


def _make_token(tenant_id: uuid.UUID, role: str, sub: uuid.UUID) -> str:
    return jwt.encode(
        {"tenant_id": str(tenant_id), "role": role, "sub": str(sub)},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


@pytest.fixture
def token_a(tenant_a: Tenant, user_a: User) -> str:
    return _make_token(tenant_a.id, "CUSTOMER", user_a.id)


@pytest.fixture
def token_b(tenant_b: Tenant, user_b: User) -> str:
    return _make_token(tenant_b.id, "COMMERCIAL", user_b.id)


@pytest.fixture
def token_commercial_a(tenant_a: Tenant, user_commercial_a: User) -> str:
    """Token for commercial user in tenant_a (for booking flow tests)."""
    return _make_token(tenant_a.id, "COMMERCIAL", user_commercial_a.id)


@pytest.fixture
def user_operations_a(db_super: Session, tenant_a: Tenant) -> User:
    """Operations user in tenant_a (for fulfillment / service orders)."""
    uid = uuid.uuid4().hex[:8]
    u = User(
        tenant_id=tenant_a.id,
        email=f"ops_a_{uid}@tenant-a.test",
        hashed_password=TEST_PASSWORD_HASH,
        full_name="Operations A",
        role=UserRole.OPERATIONS,
    )
    db_super.add(u)
    db_super.commit()
    db_super.refresh(u)
    return u


@pytest.fixture
def token_operations_a(tenant_a: Tenant, user_operations_a: User) -> str:
    return _make_token(tenant_a.id, "OPERATIONS", user_operations_a.id)


@pytest.fixture
def user_finance_a(db_super: Session, tenant_a: Tenant) -> User:
    """Finance user in tenant_a (for approve/reject payment - SoD)."""
    uid = uuid.uuid4().hex[:8]
    u = User(
        tenant_id=tenant_a.id,
        email=f"finance_a_{uid}@tenant-a.test",
        hashed_password=TEST_PASSWORD_HASH,
        full_name="Finance A",
        role=UserRole.FINANCE,
    )
    db_super.add(u)
    db_super.commit()
    db_super.refresh(u)
    return u


@pytest.fixture
def token_finance_a(tenant_a: Tenant, user_finance_a: User) -> str:
    return _make_token(tenant_a.id, "FINANCE", user_finance_a.id)


@pytest.fixture
def user_superadmin_a(db_super: Session, tenant_a: Tenant) -> User:
    """SUPERADMIN en tenant_a (gestión multi-tenant / settings)."""
    uid = uuid.uuid4().hex[:8]
    u = User(
        tenant_id=tenant_a.id,
        email=f"superadmin_a_{uid}@tenant-a.test",
        hashed_password=TEST_PASSWORD_HASH,
        full_name="SuperAdmin A",
        role=UserRole.SUPERADMIN,
    )
    db_super.add(u)
    db_super.commit()
    db_super.refresh(u)
    return u


@pytest.fixture
def token_superadmin_a(tenant_a: Tenant, user_superadmin_a: User) -> str:
    return _make_token(tenant_a.id, "SUPERADMIN", user_superadmin_a.id)


@pytest.fixture
def user_customer2_a(db_super: Session, tenant_a: Tenant) -> User:
    """Second CUSTOMER in tenant_a (e.g. for testing owner-only cancel)."""
    uid = uuid.uuid4().hex[:8]
    u = User(
        tenant_id=tenant_a.id,
        email=f"customer2_a_{uid}@tenant-a.test",
        hashed_password=TEST_PASSWORD_HASH,
        full_name="Customer Two A",
        role=UserRole.CUSTOMER,
    )
    db_super.add(u)
    db_super.commit()
    db_super.refresh(u)
    return u


@pytest.fixture
def token_customer2_a(tenant_a: Tenant, user_customer2_a: User) -> str:
    return _make_token(tenant_a.id, "CUSTOMER", user_customer2_a.id)
