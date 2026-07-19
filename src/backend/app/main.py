"""FastAPI application factory and router registration."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import settings

# Middlewares
from app.core.middleware import TenantMiddleware
from app.core.rate_limit import (
    default_rate_limit_state_middleware,
    limiter,
    rate_limit_exceeded_handler,
)

# Module routers
from app.api.public import router as public_router
from app.modules.identity.router import router as identity_router
from app.modules.access.router import router as access_router
from app.modules.booking.router import router as booking_router
from app.modules.system.router import router as system_router
from app.modules.pricing.router import router as pricing_router
from app.modules.analytics.router import router as analytics_router
from app.modules.crm.router import router as crm_router
from app.modules.fulfillment.router import router as fulfillment_router
from app.modules.finance.router import router as finance_router
from app.modules.finance.credits_router import router as finance_credits_router
from app.modules.notifications.router import router as notifications_router
from app.modules.inventory.router import router as inventory_router
from app.modules.uma_rates.router import router as uma_rates_router
from app.modules.discounts.router import router as discounts_router
from app.modules.operations.router import router as operations_router
from app.modules.reservation_documents.router import router as reservation_documents_router
from app.api.webhooks import router as webhooks_router

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
        docs_url=f"{settings.API_V1_PREFIX}/docs",
        redoc_url=f"{settings.API_V1_PREFIX}/redoc",
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    )

    # ------------------------------------------------------------------ #
    # Middleware
    # ------------------------------------------------------------------ #
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TenantMiddleware)

    # Rate limiting (PR#10, REQ-012): per-IP throttling on the public
    # (no-JWT) `/api/public/quote-requests*` endpoints. See
    # `app/core/rate_limit.py` for the key function (real client IP behind
    # nginx) and fail-open behavior on Redis outage.
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_middleware(BaseHTTPMiddleware, dispatch=default_rate_limit_state_middleware)
    app.add_middleware(SlowAPIMiddleware)

    # ------------------------------------------------------------------ #
    # Routers
    # ------------------------------------------------------------------ #
    # We shouldn't use prefix=api_prefix for ALL routers if they already have a prefix.
    # The original code just included them: app.include_router(public_router)
    app.include_router(public_router)
    app.include_router(webhooks_router)
    app.include_router(identity_router)
    app.include_router(inventory_router)
    app.include_router(booking_router)
    app.include_router(crm_router)
    app.include_router(fulfillment_router)
    app.include_router(finance_router)
    app.include_router(finance_credits_router)
    app.include_router(pricing_router)
    app.include_router(uma_rates_router)
    app.include_router(analytics_router)
    app.include_router(discounts_router)
    app.include_router(operations_router)
    app.include_router(reservation_documents_router)
    app.include_router(notifications_router)
    app.include_router(access_router)

    # System / infrastructure endpoints (no auth required)
    # the new system router seems to be included separately in the new code
    app.include_router(system_router, prefix=settings.API_V1_PREFIX)

    logger.info(
        "%s started. Health endpoint: %s/system/health",
        settings.APP_NAME,
        settings.API_V1_PREFIX,
    )
    
    @app.on_event("startup")
    def startup() -> None:
        from app.modules.fulfillment.dispatcher import FulfillmentEventDispatcher
        app.state.event_dispatcher = FulfillmentEventDispatcher()

    return app


app = create_app()
