"""Pydantic schemas for system health endpoint."""

from datetime import datetime
from typing import Optional
from enum import Enum

from pydantic import BaseModel, Field


class ServiceStatus(str, Enum):
    """Status of an individual service."""

    OK = "ok"
    ERROR = "error"


class OverallStatus(str, Enum):
    """Overall system health status."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


class ServiceHealthResult(BaseModel):
    """Health result for a single service."""

    status: ServiceStatus = Field(..., description="Service status: ok or error")
    detail: Optional[str] = Field(
        default=None,
        description="Additional detail, especially on error",
    )


class ServicesHealth(BaseModel):
    """Health results for all monitored services."""

    postgres: ServiceHealthResult = Field(..., description="PostgreSQL health")


class HealthResponse(BaseModel):
    """Response schema for GET /api/v1/system/health."""

    status: OverallStatus = Field(
        ...,
        description="Overall system status: 'healthy' if all services OK, 'unhealthy' if PostgreSQL fails",
    )
    services: ServicesHealth = Field(..., description="Per-service health details")
    timestamp: datetime = Field(
        ..., description="UTC timestamp of the health check"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "healthy",
                "services": {
                    "postgres": {"status": "ok", "detail": None},
                },
                "timestamp": "2024-01-15T12:00:00.000000Z",
            }
        }
    }
