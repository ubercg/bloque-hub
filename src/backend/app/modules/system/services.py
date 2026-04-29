"""Health check service functions for PostgreSQL."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.system.schemas import (
    HealthResponse,
    OverallStatus,
    ServiceHealthResult,
    ServiceStatus,
    ServicesHealth,
)

logger = logging.getLogger(__name__)

_HEALTH_CHECK_TIMEOUT_SECONDS = 3.0


async def check_postgres_health(db: Session) -> ServiceHealthResult:
    """
    Check PostgreSQL connectivity by executing a raw 'SELECT 1'.

    No RLS or tenant_id is applied — this is a raw infrastructure probe.

    Args:
        db: A sync SQLAlchemy session (no tenant context required).

    Returns:
        ServiceHealthResult with status 'ok' or 'error'.
    """
    try:

        def _probe() -> None:
            db.execute(text("SELECT 1"))

        await asyncio.to_thread(_probe)
        logger.debug("PostgreSQL health check passed.")
        return ServiceHealthResult(status=ServiceStatus.OK, detail=None)
    except asyncio.TimeoutError:
        detail = f"PostgreSQL did not respond within {_HEALTH_CHECK_TIMEOUT_SECONDS}s"
        logger.warning("PostgreSQL health check timed out: %s", detail)
        return ServiceHealthResult(status=ServiceStatus.ERROR, detail=detail)
    except Exception as exc:  # noqa: BLE001
        detail = f"PostgreSQL error: {exc!s}"
        logger.warning("PostgreSQL health check failed: %s", detail)
        return ServiceHealthResult(status=ServiceStatus.ERROR, detail=detail)


def compute_overall_status(postgres: ServiceHealthResult) -> OverallStatus:
    """
    Compute the overall system status from individual service results.

    Rules:
    - 'unhealthy'  → PostgreSQL is down (critical service).
    - 'healthy'    → All services OK.

    Args:
        postgres: Health result for PostgreSQL.

    Returns:
        OverallStatus enum value.
    """
    if postgres.status == ServiceStatus.ERROR:
        return OverallStatus.UNHEALTHY
    return OverallStatus.HEALTHY


async def get_system_health(db: Session) -> HealthResponse:
    """
    Run health checks and build the HealthResponse.

    Args:
        db: Sync SQLAlchemy session for PostgreSQL probe.

    Returns:
        HealthResponse with overall status, per-service details, and timestamp.
    """
    postgres_result = await check_postgres_health(db)

    overall = compute_overall_status(postgres_result)

    return HealthResponse(
        status=overall,
        services=ServicesHealth(
            postgres=postgres_result,
        ),
        timestamp=datetime.now(tz=timezone.utc),
    )
