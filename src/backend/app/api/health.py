"""Health check endpoint for system services.

Exposes GET /api/v1/system/health as a public, unauthenticated endpoint
that reports the connectivity status of PostgreSQL.

No tenant context, RLS, or JWT is required or applied.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class ServiceStatus(BaseModel):
    """Status of a single downstream service."""

    status: str  # 'ok' | 'error'
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    """Top-level health check response."""

    status: str  # 'healthy' | 'degraded'
    services: dict[str, ServiceStatus]
    timestamp: datetime


# ---------------------------------------------------------------------------
# Individual service checks
# ---------------------------------------------------------------------------

CHECK_TIMEOUT_SECONDS = 5


async def check_postgres(db: Session) -> ServiceStatus:
    """Ping PostgreSQL with a minimal SELECT 1 query.

    No RLS context or tenant_id is applied — this is a raw connectivity check.

    Args:
        db: SQLAlchemy session injected by FastAPI dependency.

    Returns:
        ServiceStatus with status='ok' on success or status='error' on failure.
        The 'detail' field contains only the exception type name, never
        connection strings or credentials.
    """
    try:
        loop = asyncio.get_event_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, lambda: db.execute(text("SELECT 1"))),
            timeout=CHECK_TIMEOUT_SECONDS,
        )
        return ServiceStatus(status="ok")
    except asyncio.TimeoutError:
        logger.warning("PostgreSQL health check timed out")
        return ServiceStatus(status="error", detail="TimeoutError")
    except Exception as exc:  # noqa: BLE001
        logger.warning("PostgreSQL health check failed: %s", type(exc).__name__)
        return ServiceStatus(status="error", detail=type(exc).__name__)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System health check",
    description=(
        "Returns the connectivity status of PostgreSQL. "
        "This endpoint is public and does not require authentication."
    ),
    tags=["system"],
    responses={
        200: {"description": "All services are healthy"},
        503: {"description": "One or more services are degraded"},
    },
)
async def get_health(db: Session = Depends(get_db)) -> JSONResponse:
    """Check the health of all downstream services.

    Runs PostgreSQL check and returns the result.
    Returns HTTP 200 when all services report 'ok', HTTP 503 otherwise.
    """
    postgres_status = await check_postgres(db)

    services = {
        "postgres": postgres_status,
    }

    all_ok = all(svc.status == "ok" for svc in services.values())
    has_error = any(svc.status == "error" for svc in services.values())

    overall_status = "degraded" if has_error else "healthy"
    http_status = status.HTTP_503_SERVICE_UNAVAILABLE if has_error else status.HTTP_200_OK

    payload = HealthResponse(
        status=overall_status,
        services=services,
        timestamp=datetime.now(tz=timezone.utc),
    )

    return JSONResponse(
        content=payload.model_dump(mode="json"),
        status_code=http_status,
    )
