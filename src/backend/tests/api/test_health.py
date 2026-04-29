"""Unit tests for GET /api/v1/system/health.

Tests cover:
- All services healthy → HTTP 200, status='healthy'
- PostgreSQL error → HTTP 503, status='degraded'
- Timeout handling for PostgreSQL
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.health import (
    ServiceStatus,
    check_postgres,
    router,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db() -> MagicMock:
    """Return a minimal SQLAlchemy Session mock."""
    db = MagicMock(spec=Session)
    db.execute.return_value = MagicMock()
    return db


# ---------------------------------------------------------------------------
# Unit tests — check_postgres
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_postgres_ok():
    db = _make_db()
    result = await check_postgres(db)
    assert result.status == "ok"
    assert result.detail is None


@pytest.mark.asyncio
async def test_check_postgres_error():
    db = _make_db()
    db.execute.side_effect = Exception("connection refused")
    result = await check_postgres(db)
    assert result.status == "error"
    # detail must NOT contain the raw message / connection string
    assert result.detail == "Exception"


@pytest.mark.asyncio
async def test_check_postgres_timeout():
    import asyncio

    db = _make_db()

    async def _slow(*_):
        await asyncio.sleep(10)

    with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
        result = await check_postgres(db)

    assert result.status == "error"
    assert result.detail == "TimeoutError"


# ---------------------------------------------------------------------------
# Integration-style tests via TestClient
# ---------------------------------------------------------------------------


def _build_test_app():
    """Build a minimal FastAPI app with only the health router."""
    from fastapi import FastAPI
    from app.db.session import get_db

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/system")

    db_mock = _make_db()
    app.dependency_overrides[get_db] = lambda: db_mock
    return app, db_mock


def test_health_endpoint_all_ok():
    app, _ = _build_test_app()

    with patch(
        "app.api.health.check_postgres",
        new=AsyncMock(return_value=ServiceStatus(status="ok")),
    ):
        client = TestClient(app)
        response = client.get("/api/v1/system/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["services"]["postgres"]["status"] == "ok"
    assert "timestamp" in body


def test_health_endpoint_postgres_error():
    app, _ = _build_test_app()

    with patch(
        "app.api.health.check_postgres",
        new=AsyncMock(
            return_value=ServiceStatus(status="error", detail="OperationalError")
        ),
    ):
        client = TestClient(app)
        response = client.get("/api/v1/system/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["services"]["postgres"]["status"] == "error"
    assert body["services"]["postgres"]["detail"] == "OperationalError"


def test_health_response_never_leaks_credentials():
    """Ensure the detail field does not contain connection strings."""
    app, _ = _build_test_app()

    with patch(
        "app.api.health.check_postgres",
        new=AsyncMock(
            return_value=ServiceStatus(
                status="error", detail="OperationalError"
            )
        ),
    ):
        client = TestClient(app)
        response = client.get("/api/v1/system/health")

    body = response.json()
    detail = body["services"]["postgres"].get("detail", "")
    assert "://" not in (detail or ""), "detail must not contain a URL/connection string"
    assert "password" not in (detail or "").lower()
