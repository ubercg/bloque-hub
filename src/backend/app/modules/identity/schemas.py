from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.modules.identity.models import UserRole

# Slug URL-seguro (alineado con uso en catálogo / seed --tenant-slug)
TENANT_SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class TenantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=TENANT_SLUG_PATTERN,
        description="Solo minúsculas, números y guiones; p. ej. bloque-hub",
    )
    max_discount_threshold: float | None = Field(
        None,
        ge=0,
        le=100,
        description="Umbral máximo de descuento (%) para el tenant; default 0 si se omite",
    )


class TenantRead(BaseModel):
    id: UUID
    name: str
    slug: str
    is_active: bool
    max_discount_threshold: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TenantUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    slug: str | None = Field(
        None,
        min_length=1,
        max_length=64,
        pattern=TENANT_SLUG_PATTERN,
    )
    is_active: bool | None = None
    max_discount_threshold: float | None = Field(None, ge=0, le=100)


class UserCreate(BaseModel):
    tenant_id: UUID
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=1, max_length=255)
    role: UserRole = UserRole.CUSTOMER


class UserRead(BaseModel):
    id: UUID
    tenant_id: UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# Login schemas

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead
    tenant_id: UUID
