from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from fastapi import Request
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base

# Usar APP_DATABASE_URL (usuario no superuser, ej. bloque_app) cuando exista para que RLS se aplique
_db_url = getattr(settings, "APP_DATABASE_URL", None) or settings.DATABASE_URL

engine = create_engine(
    _db_url,
    pool_pre_ping=True,
    echo=False,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _set_tenant_on_connection(
    session: Session, tenant_id: str | None, role: str | None
) -> None:
    # Use session.execute so the same transaction is used for subsequent queries
    if tenant_id is not None:
        session.execute(
            text("SET LOCAL app.current_tenant_id = :tid"), {"tid": tenant_id}
        )
    if role is not None:
        session.execute(text("SET LOCAL app.role = :role"), {"role": role})


def _rls_after_begin(session: Session, _transaction: Any, connection: Any) -> None:
    """Re-apply RLS session vars at start of each transaction (for get_db_context)."""
    tid = session.info.get("rls_tenant_id")
    role = session.info.get("rls_role")
    if tid is not None:
        connection.execute(text("SET LOCAL app.current_tenant_id = :tid"), {"tid": tid})
    if role is not None:
        connection.execute(text("SET LOCAL app.role = :role"), {"role": role})


def get_db(request: Request) -> Generator[Session, Any, None]:
    """Dependency that yields a DB session and sets app.current_tenant_id from request.state.
    Uses after_begin so SET LOCAL is re-applied at the start of every transaction (e.g. after commit)."""
    db = SessionLocal()
    rls_enabled = False
    try:
        tenant_id: str | None = None
        role: str | None = None
        if hasattr(request.state, "tenant_id") and request.state.tenant_id is not None:
            tenant_id = str(request.state.tenant_id)
        if hasattr(request.state, "role") and request.state.role is not None:
            role = str(request.state.role)
        if tenant_id is not None or role is not None:
            db.info["rls_tenant_id"] = tenant_id
            db.info["rls_role"] = role
            event.listen(db, "after_begin", _rls_after_begin)
            rls_enabled = True
            _set_tenant_on_connection(db, tenant_id, role)
        yield db
    finally:
        if rls_enabled:
            event.remove(db, "after_begin", _rls_after_begin)
        db.close()


@contextmanager
def get_db_context(
    tenant_id: str | None = None, role: str | None = None
) -> Generator[Session, Any, None]:
    """Context manager for use outside request (e.g. scripts, tests). Optionally set tenant/role.
    Uses after_begin so SET LOCAL runs at the start of every transaction (including after commit)."""
    db = SessionLocal()
    try:
        tid_str = str(tenant_id) if tenant_id is not None else None
        role_str = str(role) if role is not None else None
        if tid_str is not None or role_str is not None:
            db.info["rls_tenant_id"] = tid_str
            db.info["rls_role"] = role_str
            event.listen(db, "after_begin", _rls_after_begin)
            _set_tenant_on_connection(db, tid_str, role_str)
        yield db
    finally:
        event.remove(db, "after_begin", _rls_after_begin)
        db.close()
