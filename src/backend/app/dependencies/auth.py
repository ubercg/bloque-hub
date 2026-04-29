from typing import Annotated
from uuid import UUID

from fastapi import Query, Request, status
from fastapi.exceptions import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import (
    ALLOWED_APPROVE_REJECT_PAYMENT_ROLES,
    ALLOWED_EVIDENCE_UPLOAD_ROLES as PERM_EVIDENCE,
    ALLOWED_FINANCE_ROLES as PERM_FINANCE,
    ALLOWED_GENERATE_SLIP_ROLES,
    ALLOWED_OPERATIONS_ROLES as PERM_OPERATIONS,
)
from app.db.session import SessionLocal

ALLOWED_CONFIRM_REJECT_ROLES = ALLOWED_GENERATE_SLIP_ROLES  # generate_slip: COMMERCIAL/FINANCE/SUPERADMIN
ALLOWED_OPERATIONS_ROLES = PERM_OPERATIONS
ALLOWED_EVIDENCE_UPLOAD_ROLES = PERM_EVIDENCE
ALLOWED_FINANCE_ROLES = PERM_FINANCE


def require_tenant(request: Request) -> tuple[UUID, str | None]:
    """Dependency that requires request.state.tenant_id to be set. Returns (tenant_id, role)."""
    if not getattr(request.state, "tenant_id", None):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    role = getattr(request.state, "role", None)
    return request.state.tenant_id, role


def optional_tenant_for_catalog(request: Request) -> tuple[UUID, str | None]:
    """Catalog tenant resolution for GET /api/spaces (and related read-only catalog endpoints).

    - If the request carries a valid JWT, uses request.state.tenant_id (set by TenantMiddleware)
      so RLS returns only that tenant's spaces. The frontend MUST send Authorization: Bearer <token>
      when the user is logged in so that authenticated users only see their tenant's catalog.
    - If Authorization: Bearer is present but the token is invalid or expired, returns 401 so the
      frontend can clear session and redirect to login (avoids showing another tenant's catalog).
    - If there is no JWT (anonymous access): if query params tenant_id or sede (slug) are present,
      resolve that tenant and use it; otherwise use default tenant (DEFAULT_TENANT_ID or first).
    """
    if getattr(request.state, "tenant_id", None):
        role = getattr(request.state, "role", None)
        # SUPERADMIN puede forzar sede con ?tenant_id= para catálogo / gestión multi-tenant
        if role == "SUPERADMIN":
            q_override = request.query_params.get("tenant_id")
            if q_override:
                try:
                    request.state.tenant_id = UUID(q_override)
                except (ValueError, TypeError):
                    pass
        return request.state.tenant_id, role
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.strip().lower().startswith("bearer ") and auth_header.strip()[7:].strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    # Anonymous: allow query params tenant_id (UUID) or sede (slug) for public catalog
    from app.modules.identity.models import Tenant
    q_tenant_id = request.query_params.get("tenant_id")
    q_sede = request.query_params.get("sede")
    resolved_id: UUID | None = None
    if q_tenant_id:
        try:
            resolved_id = UUID(q_tenant_id)
        except (ValueError, TypeError):
            pass
    if resolved_id is None and q_sede and q_sede.strip():
        db_lookup: Session = SessionLocal()
        try:
            row = db_lookup.execute(
                select(Tenant.id).where(
                    Tenant.slug == q_sede.strip(),
                    Tenant.is_active.is_(True),
                ).limit(1)
            ).scalars().first()
            if row is not None:
                resolved_id = row
        finally:
            db_lookup.close()
    if resolved_id is not None:
        request.state.tenant_id = resolved_id
        request.state.role = getattr(request.state, "role", None)
        return resolved_id, request.state.role
    # Fallback: default tenant
    default_id: UUID | None = None
    if settings.DEFAULT_TENANT_ID:
        try:
            default_id = UUID(settings.DEFAULT_TENANT_ID)
        except (ValueError, TypeError):
            pass
    if default_id is None:
        db: Session = SessionLocal()
        try:
            row = db.execute(select(Tenant.id).limit(1)).scalars().first()
            if row is not None:
                default_id = row
        finally:
            db.close()
    if default_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    request.state.tenant_id = default_id
    request.state.role = getattr(request.state, "role", None)
    return default_id, request.state.role


def require_commercial_or_admin(request: Request) -> None:
    """Dependency that requires role COMMERCIAL, FINANCE or SUPERADMIN (e.g. generate_slip). Use with require_tenant."""
    role = getattr(request.state, "role", None)
    if role not in ALLOWED_CONFIRM_REJECT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient role for this operation",
        )


def require_finance_approval(request: Request) -> None:
    """Dependency that requires role FINANCE or SUPERADMIN for approving/rejecting payments (SoD). Use with require_tenant."""
    role = getattr(request.state, "role", None)
    if role not in ALLOWED_APPROVE_REJECT_PAYMENT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Finance or SuperAdmin can approve or reject payments",
        )


def require_operations_or_admin(request: Request) -> None:
    """Dependency that requires role OPERATIONS or SUPERADMIN (for service orders). Use with require_tenant."""
    role = getattr(request.state, "role", None)
    if role not in ALLOWED_OPERATIONS_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient role to manage service orders",
        )


def require_evidence_upload(request: Request) -> None:
    """Dependency that allows COMMERCIAL, OPERATIONS or SUPERADMIN to upload evidence. Use with require_tenant."""
    role = getattr(request.state, "role", None)
    if role not in ALLOWED_EVIDENCE_UPLOAD_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient role to upload evidence",
        )


def require_finance_or_admin(request: Request) -> None:
    """Dependency that requires role FINANCE or SUPERADMIN (for CFDI, conciliación). Use with require_tenant."""
    role = getattr(request.state, "role", None)
    if role not in ALLOWED_FINANCE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient role for finance operations",
        )


def require_superadmin(request: Request) -> None:
    """Dependency that requires role SUPERADMIN (e.g. list tenants). Use with require_tenant."""
    role = getattr(request.state, "role", None)
    if role != "SUPERADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SuperAdmin role required",
        )


def resolve_staff_space_tenant_id(
    request: Request,
    tenant_id: Annotated[UUID | None, Query(alias="tenant_id")] = None,
) -> UUID:
    """Tenant destino para crear espacios (staff). SUPERADMIN puede pasar ?tenant_id= para otra sede."""
    role = getattr(request.state, "role", None)
    jwt_tid = getattr(request.state, "tenant_id", None)
    if tenant_id is not None:
        if role != "SUPERADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only SUPERADMIN may set tenant_id query param",
            )
        return tenant_id
    if jwt_tid is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return jwt_tid


def assert_space_mutable_by_requester(request: Request, space_tenant_id: UUID) -> None:
    """No-SUPERADMIN solo muta espacios de su JWT tenant_id."""
    role = getattr(request.state, "role", None)
    if role == "SUPERADMIN":
        return
    jwt_tid = getattr(request.state, "tenant_id", None)
    if jwt_tid is None or space_tenant_id != jwt_tid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Space not found")
