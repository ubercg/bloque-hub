"""Endpoints para créditos (saldos a favor). Requieren rol FINANCE o SUPERADMIN."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.exceptions import HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import require_finance_or_admin, require_tenant
from app.modules.finance.credit_balances import apply_credit_to_reservation, get_available_credits
from app.modules.finance.schemas import CreditApplyBody, CreditBalanceRead

router = APIRouter(prefix="/api/finance", tags=["finance-credits"])


@router.get("/credits", response_model=list[CreditBalanceRead])
def list_credits(
    request: Request,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
    __: None = Depends(require_finance_or_admin),
):
    """Lista créditos con saldo disponible para el tenant (para gestión de notas de crédito)."""
    tenant_id = request.state.tenant_id
    credits = get_available_credits(db, tenant_id=tenant_id)
    return [CreditBalanceRead.model_validate(c) for c in credits]


@router.post("/credits/{credit_id}/apply", response_model=CreditBalanceRead)
def apply_credit(
    request: Request,
    credit_id: UUID,
    body: CreditApplyBody,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
    __: None = Depends(require_finance_or_admin),
):
    """Aplica un crédito (saldo a favor) a una reserva. No permite aplicar el mismo crédito dos veces."""
    tenant_id = request.state.tenant_id
    updated = apply_credit_to_reservation(
        db,
        credit_id=credit_id,
        reservation_id=body.reservation_id,
        monto_a_aplicar=body.monto_a_aplicar,
    )
    if updated is None:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo aplicar el crédito (saldo insuficiente, crédito ya aplicado o no encontrado)",
        )
    db.commit()
    db.refresh(updated)
    return CreditBalanceRead.model_validate(updated)
