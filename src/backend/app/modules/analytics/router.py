import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.session import get_db
from app.dependencies.auth import require_tenant, require_commercial_or_admin
from app.modules.analytics.metrics_service import get_all_krs

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])

class MetricsResponse(BaseModel):
    kr23: float
    kr24: float
    kr25: float
    kr26: float
    kr27: float

@router.get("", response_model=MetricsResponse)
def fetch_krs(
    db: Session = Depends(get_db),
    tenant_info: tuple[uuid.UUID, str] = Depends(require_tenant)
):
    tenant_id, _ = tenant_info
    metrics = get_all_krs(db, tenant_id)
    return metrics
