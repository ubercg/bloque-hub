import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import require_commercial_or_admin, require_tenant
from app.modules.uma_rates import services
from app.modules.uma_rates.models import UMARate
from app.modules.uma_rates.schemas import UmaRateCreate, UmaRateResponse

router = APIRouter(prefix="/api/uma-rates", tags=["UMA Rates"])


@router.post("/", response_model=UmaRateResponse, status_code=status.HTTP_201_CREATED)
def create_uma_rate_endpoint(
    request: Request,
    rate_in: UmaRateCreate,
    db: Session = Depends(get_db),
    tenant_info: tuple[uuid.UUID, str] = Depends(require_tenant),
    _: None = Depends(require_commercial_or_admin),
):
    tenant_id, _ = tenant_info
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User context required to register UMA rate",
        )
    try:
        created = services.register_uma_rate(
            value=rate_in.value,
            effective_date=rate_in.effective_date,
            user_id=user_id,
            tenant_id=tenant_id,
            db=db,
        )
        db.commit()
        db.refresh(created)
        return created
    except services.UmaRateConflictException as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception:
        db.rollback()
        raise


@router.get("/", response_model=List[UmaRateResponse])
def get_uma_rates_endpoint(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    tenant_info: tuple[uuid.UUID, str] = Depends(require_tenant),
    _: None = Depends(require_commercial_or_admin),
):
    tenant_id, _ = tenant_info
    return (
        db.query(UMARate)
        .filter(UMARate.tenant_id == tenant_id)
        .order_by(desc(UMARate.effective_date))
        .offset(skip)
        .limit(limit)
        .all()
    )
