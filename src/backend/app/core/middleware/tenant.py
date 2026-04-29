import uuid
from typing import Callable

import jwt
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings


class TenantMiddleware(BaseHTTPMiddleware):
    """Extracts tenant_id and role from JWT and sets them on request.state."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request.state.tenant_id = None
        request.state.role = None
        request.state.user_id = None

        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            if token:
                try:
                    payload = jwt.decode(
                        token,
                        settings.SECRET_KEY,
                        algorithms=[settings.ALGORITHM],
                    )
                    raw_tenant = payload.get("tenant_id")
                    if raw_tenant is not None:
                        request.state.tenant_id = (
                            uuid.UUID(str(raw_tenant))
                            if not isinstance(raw_tenant, uuid.UUID)
                            else raw_tenant
                        )
                    raw_role = payload.get("role")
                    if raw_role is not None:
                        request.state.role = str(raw_role)
                    raw_sub = payload.get("sub")
                    if raw_sub is not None:
                        try:
                            request.state.user_id = (
                                uuid.UUID(str(raw_sub))
                                if not isinstance(raw_sub, uuid.UUID)
                                else raw_sub
                            )
                        except (ValueError, TypeError):
                            pass
                except jwt.PyJWTError:
                    pass

        return await call_next(request)
