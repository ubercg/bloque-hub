import logging
import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.exceptions import DomainException
from app.modules.audit.service import append_audit_log
from app.modules.uma_rates.models import UMARate

logger = logging.getLogger(__name__)


class UmaRateConflictException(DomainException):
    def __init__(self, message="UMA rate already exists for this effective date"):
        super().__init__(status_code=400, detail=message)


class UmaRateNotFoundException(DomainException):
    def __init__(self, message="UMA rate not found"):
        super().__init__(status_code=404, detail=message)


def get_current_uma(
    tenant_id: uuid.UUID, target_date: Optional[date] = None, db: Session = None
) -> UMARate:
    """Última UMA con effective_date <= target_date (append-only por fecha efectiva)."""
    dt = target_date or date.today()
    rate = (
        db.query(UMARate)
        .filter(
            UMARate.tenant_id == tenant_id,
            UMARate.effective_date <= dt,
        )
        .order_by(desc(UMARate.effective_date))
        .first()
    )
    if not rate:
        raise UmaRateNotFoundException(f"No UMA rate found effective on {dt}")
    return rate


def register_uma_rate(
    value: Decimal,
    effective_date: date,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    db: Session,
) -> UMARate:
    """Registra una fila UMA (append-only). Conflicto si ya existe (tenant_id, effective_date)."""
    existing = (
        db.query(UMARate)
        .filter(
            UMARate.tenant_id == tenant_id,
            UMARate.effective_date == effective_date,
        )
        .first()
    )
    if existing:
        raise UmaRateConflictException("UMA rate already exists for this effective date")

    db_rate = UMARate(
        tenant_id=tenant_id,
        value=value,
        effective_date=effective_date,
        created_by=user_id,
    )
    db.add(db_rate)
    db.flush()

    append_audit_log(
        db=db,
        tenant_id=tenant_id,
        tabla="uma_rates",
        registro_id=db_rate.id,
        accion="INSERT",
        valor_nuevo={
            "value": str(db_rate.value),
            "effective_date": str(db_rate.effective_date),
            "created_by": str(user_id),
        },
        actor_id=user_id,
    )

    return db_rate
