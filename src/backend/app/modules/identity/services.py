# Authentication services for login and JWT creation

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import bcrypt
import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.identity.models import User, UserRole
from app.db.session import get_db_context
from app.modules.identity.schemas import UserCreate, UserUpdate


class DuplicateEmailError(Exception):
    pass


class LastSuperadminLockoutError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


def get_password_hash(plain_password: str) -> str:
    """Hash password con bcrypt (para registro y seed de usuarios de prueba)."""
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verificar password contra hash bcrypt."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """
    Autenticar usuario por email y password.
    Retorna User si credenciales válidas y usuario activo.
    Retorna None en caso contrario (no revela si el usuario existe).
    """
    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def create_access_token(user: User) -> str:
    """
    Crear JWT con claims para TenantMiddleware.
    Claims: tenant_id, role, sub, exp, iat.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "tenant_id": str(user.tenant_id),
        "role": user.role.value,
        "sub": str(user.id),
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_user(db: Session, user_data: UserCreate) -> User:
    # Everything runs under an elevated context to allow creating users
    # in different tenants and enforcing global email uniqueness safely.
    with get_db_context(tenant_id=None, role=UserRole.SUPERADMIN.value) as super_db:
        existing_user = super_db.query(User).filter(User.email == user_data.email).first()
        if existing_user:
            raise DuplicateEmailError("Email already registered globally.")

        hashed_password = get_password_hash(user_data.password)
        db_user = User(
            tenant_id=user_data.tenant_id,
            email=user_data.email,
            hashed_password=hashed_password,
            full_name=user_data.full_name,
            role=user_data.role,
            is_active=True,  # Default to active on creation
        )
        super_db.add(db_user)
        super_db.commit()
        super_db.refresh(db_user)
    return db_user


def update_user(db: Session, user_id: UUID, user_data: UserUpdate) -> User:
    # All operations within this function must run under a single elevated context
    # to bypass RLS and ensure atomicity for tenant transfers and global checks.
    with get_db_context(tenant_id=None, role=UserRole.SUPERADMIN.value) as super_db:
        # Fetch the user to update using the elevated context
        # This bypasses RLS, allowing updates across any tenant
        user_to_update = super_db.query(User).filter(User.id == user_id).first()
        if not user_to_update:
            raise UserNotFoundError(f"User with ID {user_id} not found.")

        # Store old values for comparison, especially for role and is_active
        old_is_active = user_to_update.is_active
        old_role = user_to_update.role
        old_tenant_id = user_to_update.tenant_id

        # Apply updates from user_data
        update_fields = user_data.model_dump(exclude_unset=True)

        # Handle password separately
        if "password" in update_fields and update_fields["password"] is not None:
            user_to_update.hashed_password = get_password_hash(update_fields["password"])
            del update_fields["password"] # Remove from dict to avoid direct assignment

        # Global email uniqueness check if email is being updated
        if "email" in update_fields and update_fields["email"] is not None and update_fields["email"] != user_to_update.email:
            existing_user_with_email = super_db.query(User).filter(User.email == update_fields["email"], User.id != user_id).first()
            if existing_user_with_email:
                raise DuplicateEmailError("Email already registered globally for another user.")
            user_to_update.email = update_fields["email"]
            del update_fields["email"]

        # Update remaining fields
        for field, value in update_fields.items():
            setattr(user_to_update, field, value)

        # Lockout protection: Prevent deactivating or changing role of the last active SUPERADMIN in a tenant
        # This check is performed using the *elevated context* to accurately count SUPERADMINs
        # across tenants if a transfer is also occurring.
        # Check only if is_active or role is changing, and the user was a SUPERADMIN
        is_changing_status_or_role = (user_data.is_active is not None and user_data.is_active is False and old_is_active is True) or \
                                     (user_data.role is not None and user_data.role != old_role) or \
                                     (user_data.tenant_id is not None and user_data.tenant_id != old_tenant_id and old_role == UserRole.SUPERADMIN)

        if is_changing_status_or_role and old_role == UserRole.SUPERADMIN:
            # Count active SUPERADMINs in the ORIGINAL tenant
            active_superadmins_in_tenant = super_db.query(User).filter(
                User.tenant_id == old_tenant_id,
                User.role == UserRole.SUPERADMIN,
                User.is_active == True,
                User.id != user_id # Exclude the current user from the count IF they are the one being changed
            ).count()

            # If the current user is the last active SUPERADMIN and is being deactivated,
            # or their role/tenant is being changed away from SUPERADMIN in their original tenant,
            # then block the operation.
            if active_superadmins_in_tenant == 0:
                # If the target change is making this user no longer a SUPERADMIN in their original tenant
                if (user_data.is_active is False) or \
                   (user_data.role is not None and user_data.role != UserRole.SUPERADMIN) or \
                   (user_data.tenant_id is not None and user_data.tenant_id != old_tenant_id):
                    raise LastSuperadminLockoutError("Cannot deactivate or change role/tenant of the last active SUPERADMIN.")


        super_db.add(user_to_update) # Add if it's a new instance, or just update if it's already in session
        super_db.commit()
        super_db.refresh(user_to_update) # Refresh to get latest state from DB

    return user_to_update


def delete_user(db: Session, user_id: UUID) -> User:
    """
    Deactivates a user (soft delete) with lockout protection for the last active SUPERADMIN.
    This operation runs under an elevated context to bypass RLS.
    """
    with get_db_context(tenant_id=None, role=UserRole.SUPERADMIN.value) as super_db:
        user_to_delete = super_db.query(User).filter(User.id == user_id).first()
        if not user_to_delete:
            raise UserNotFoundError(f"User with ID {user_id} not found.")

        # Lockout protection: Prevent deactivating the last active SUPERADMIN in a tenant
        if user_to_delete.role == UserRole.SUPERADMIN and user_to_delete.is_active is True:
            # Count active SUPERADMINs in this user's tenant, excluding the current user
            active_superadmins_in_tenant = super_db.query(User).filter(
                User.tenant_id == user_to_delete.tenant_id,
                User.role == UserRole.SUPERADMIN,
                User.is_active == True,
                User.id != user_id
            ).count()

            if active_superadmins_in_tenant == 0:
                raise LastSuperadminLockoutError("Cannot deactivate the last active SUPERADMIN.")

        user_to_delete.is_active = False
        super_db.add(user_to_delete)
        super_db.commit()
        super_db.refresh(user_to_delete)
    return user_to_delete

