# Authentication services for login and JWT creation

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.identity.models import User


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
