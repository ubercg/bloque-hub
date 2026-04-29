"""Router for system-level endpoints (health checks, etc.)."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.system.schemas import HealthResponse
from app.modules.system.services import get_system_health

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/system",
    tags=["system"],
)


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System health check",
    description=(
        "Returns the health status of infrastructure services (PostgreSQL). "
        "Always returns HTTP 200 — inspect the 'status' field to determine "
        "overall health: 'healthy' or 'unhealthy'."
    ),
    operation_id="get_system_health",
)
async def health_check(
    db: Session = Depends(get_db),
) -> HealthResponse:
    """
    GET /api/v1/system/health

    Probes PostgreSQL (3s timeout).
    No authentication or tenant context required.

    Returns:
        HealthResponse with overall status, per-service details, and UTC timestamp.
    """
    logger.info("System health check requested.")
    response = await get_system_health(db=db)
    logger.info(
        "System health check completed: overall_status=%s postgres=%s",
        response.status,
        response.services.postgres.status,
    )
    return response
