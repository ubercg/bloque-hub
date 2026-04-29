"""Servicios para saldo a favor (credit_balances): crear y aplicar a reserva."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.finance.models import CreditBalance


def create_credit(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    cfdi_uuid: uuid.UUID,
    monto: float,
    reservation_origen_id: uuid.UUID | None = None,
) -> CreditBalance:
    """Registra un saldo a favor vinculado al CFDI (excedente o cancelación)."""
    cred = CreditBalance(
        tenant_id=tenant_id,
        cfdi_uuid=cfdi_uuid,
        monto_original=Decimal(str(monto)),
        saldo_restante=Decimal(str(monto)),
        reservation_origen_id=reservation_origen_id,
    )
    db.add(cred)
    db.flush()
    return cred


def get_available_credits(
    db: Session,
    *,
    tenant_id: uuid.UUID,
) -> list[CreditBalance]:
    """Lista créditos con saldo_restante > 0 para el tenant."""
    stmt = (
        select(CreditBalance)
        .where(
            CreditBalance.tenant_id == tenant_id,
            CreditBalance.saldo_restante > 0,
        )
    )
    return list(db.execute(stmt).scalars().all())


def apply_credit_to_reservation(
    db: Session,
    *,
    credit_id: uuid.UUID,
    reservation_id: uuid.UUID,
    monto_a_aplicar: float,
) -> CreditBalance | None:
    """
    Aplica parte o todo el saldo a favor a una reserva.
    No permite aplicar el mismo crédito dos veces (aplicado_a_reservation_id ya usado).
    Retorna el CreditBalance actualizado o None si no hay saldo suficiente.
    """
    cred = db.get(CreditBalance, credit_id)
    if cred is None or cred.saldo_restante <= 0:
        return None
    if cred.aplicado_a_reservation_id is not None:
        return None
    aplicar = Decimal(str(min(monto_a_aplicar, float(cred.saldo_restante))))
    if aplicar <= 0:
        return None
    cred.saldo_restante -= aplicar
    cred.aplicado_a_reservation_id = reservation_id
    db.flush()
    return cred
