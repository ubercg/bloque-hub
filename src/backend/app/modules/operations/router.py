"""Operations dashboard API."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.db.session import get_db
from app.dependencies.auth import require_tenant
from app.modules.booking.models import ReservationStatus
from app.modules.operations.schemas import ReservationsSummaryResponse
from app.modules.operations.services import allow_operations_summary_role, build_reservations_summary
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/operations", tags=["operations"])


@router.get("/reservations-summary", response_model=ReservationsSummaryResponse)
def get_reservations_summary(
    request: Request,
    db: Session = Depends(get_db),
    tenant_data: tuple[UUID, str | None] = Depends(require_tenant),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    status: ReservationStatus | None = Query(None),
    space_id: UUID | None = Query(None),
):
    """
    Aggregated reservation groups with merged time blocks, KPIs for today (America/Mexico_City), and readiness flags.
    """
    tenant_id, role = tenant_data
    allow_operations_summary_role(role)
    user_id = getattr(request.state, "user_id", None)
    return build_reservations_summary(
        db,
        tenant_id=tenant_id,
        role=role,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
        status=status,
        space_id=space_id,
    )
