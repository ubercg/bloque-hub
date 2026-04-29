"""Public API endpoints (no JWT required)."""

import mimetypes
import re
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import settings
from app.db.session import get_db_context
from app.modules.identity.models import Tenant

router = APIRouter(prefix="/api", tags=["public"])

_SPACE_PROMO_FILENAME = re.compile(
    r"^[a-f0-9]{32}\.(jpe?g|png|webp|gif)$",
    re.IGNORECASE,
)


class SedeRead(BaseModel):
    """Sede (tenant) for public catalog selector."""

    id: UUID
    name: str
    slug: str

    model_config = {"from_attributes": True}


@router.get("/media/space-promo/{tenant_id}/{filename}")
def get_space_promo_media(tenant_id: UUID, filename: str):
    """
    Sirve imágenes subidas para el catálogo (hero/galería). Sin autenticación
    para que `<img src>` funcione en el catálogo público.
    """
    if not _SPACE_PROMO_FILENAME.match(filename):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    base = Path(settings.SPACE_PROMO_MEDIA_PATH) / str(tenant_id)
    path = (base / filename).resolve()
    try:
        path.relative_to(base.resolve())
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)


@router.get("/public/sedes", response_model=list[SedeRead])
def list_sedes():
    """
    List active tenants (sedes) for public catalog.
    No authentication required. Used when the user is anonymous to choose a sede
    or to show a single-sede catalog.
    """
    with get_db_context(tenant_id=None, role="SUPERADMIN") as db:
        tenants = db.query(Tenant).filter(Tenant.is_active.is_(True)).order_by(Tenant.name).all()
        return [SedeRead.model_validate(t) for t in tenants]
