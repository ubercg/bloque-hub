from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.exceptions import HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db, get_db_context
from app.dependencies.auth import require_tenant, require_superadmin
from app.modules.identity.models import Tenant, User
from app.modules.identity.schemas import (
    LoginRequest,
    LoginResponse,
    TenantCreate,
    TenantRead,
    TenantUpdate,
    UserRead,
)
from app.modules.identity import services

router = APIRouter(prefix="/api", tags=["identity"])


def _get_tenant_or_404(db: Session, tenant_id: UUID) -> Tenant:
    row = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return row


@router.post("/auth/login", response_model=LoginResponse)
def login(credentials: LoginRequest):
    """
    Autenticar usuario y retornar JWT.
    Endpoint PÚBLICO (sin JWT). Usa sesión con role SUPERADMIN para poder leer
    cualquier usuario por email (RLS bloquearía la consulta si no).
    """
    with get_db_context(tenant_id=None, role="SUPERADMIN") as db:
        user = services.authenticate_user(db, credentials.email, credentials.password)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        access_token = services.create_access_token(user)
        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            user=UserRead.model_validate(user),
            tenant_id=user.tenant_id,
        )


@router.get("/me")
def me(
    request: Request,
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Return current tenant_id and role from JWT (for testing middleware + SET LOCAL)."""
    return {
        "tenant_id": str(request.state.tenant_id),
        "role": getattr(request.state, "role", None),
        "user_id": str(request.state.user_id) if getattr(request.state, "user_id", None) else None,
    }


@router.post("/tenants", response_model=TenantRead, status_code=status.HTTP_201_CREATED)
def create_tenant(
    body: TenantCreate,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
    __: None = Depends(require_superadmin),
):
    """Crear tenant. Solo SUPERADMIN. Slug debe ser único."""
    existing = db.query(Tenant).filter(Tenant.slug == body.slug).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A tenant with this slug already exists",
        )
    t = Tenant(
        name=body.name.strip(),
        slug=body.slug.strip(),
        is_active=True,
        max_discount_threshold=body.max_discount_threshold
        if body.max_discount_threshold is not None
        else 0.0,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@router.get("/tenants", response_model=list[TenantRead])
def list_tenants(
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
    __: None = Depends(require_superadmin),
):
    """List all tenants. Requires SUPERADMIN role."""
    return db.query(Tenant).all()


@router.get("/tenants/{tenant_id}", response_model=TenantRead)
def get_tenant(
    tenant_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
    __: None = Depends(require_superadmin),
):
    """Obtener un tenant por id. Solo SUPERADMIN."""
    return _get_tenant_or_404(db, tenant_id)


@router.patch("/tenants/{tenant_id}", response_model=TenantRead)
def patch_tenant(
    tenant_id: UUID,
    body: TenantUpdate,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
    __: None = Depends(require_superadmin),
):
    """Actualizar tenant (nombre, slug, activo, umbral descuento). Sin borrado físico."""
    t = _get_tenant_or_404(db, tenant_id)
    data = body.model_dump(exclude_unset=True)
    if "slug" in data and data["slug"] is not None:
        new_slug = data["slug"].strip()
        other = (
            db.query(Tenant)
            .filter(Tenant.slug == new_slug, Tenant.id != tenant_id)
            .first()
        )
        if other is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A tenant with this slug already exists",
            )
        t.slug = new_slug
    if "name" in data and data["name"] is not None:
        t.name = data["name"].strip()
    if "is_active" in data:
        t.is_active = data["is_active"]
    if "max_discount_threshold" in data and data["max_discount_threshold"] is not None:
        t.max_discount_threshold = data["max_discount_threshold"]
    db.commit()
    db.refresh(t)
    return t


@router.get("/tenants/{tenant_id}/users", response_model=list[UserRead])
def list_tenant_users(
    tenant_id: UUID,
    _: tuple[UUID, str | None] = Depends(require_tenant),
    __: None = Depends(require_superadmin),
):
    """List users of a specific tenant. Requires SUPERADMIN role."""
    with get_db_context(tenant_id=tenant_id, role="SUPERADMIN") as db:
        users = db.query(User).filter(User.tenant_id == tenant_id).all()
        return users


@router.get("/users", response_model=list[UserRead])
def list_users(
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """List users in the current tenant (RLS applies)."""
    users = db.query(User).all()
    return users


@router.get("/users/{user_id}", response_model=UserRead)
def get_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Get one user by id. RLS ensures only users of the current tenant are visible (404 otherwise)."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user
