from fastapi import APIRouter

from app.api.v1.endpoints import (
    users,
    tenants,
    auth,
    booking,
    audit,
    uma_rates # New import
)

api_router = APIRouter()
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(booking.router, prefix="/booking",