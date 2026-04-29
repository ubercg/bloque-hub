"""Endpoints CFDI (estado por reserva)."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import require_finance_or_admin
from app.modules.finance.models import CfdiDocument
from app.modules.finance.schemas import CfdiDocumentRead

router = APIRouter(prefix="/api/cfdi", tags=["cfdi"])


@router.get("/reservations/{reservation_id}", response_model=list[CfdiDocumentRead])
def list_cfdi_by_reservation(
    reservation_id: UUID,
    _: None = Depends(require_finance_or_admin),
    db: Session = Depends(get_db),
) -> list[CfdiDocumentRead]:
    """Lista CFDIs asociados a una reserva (para Dashboard Finanzas)."""
    stmt = select(CfdiDocument).where(CfdiDocument.reservation_id == reservation_id)
    rows = db.execute(stmt).scalars().all()
    return [CfdiDocumentRead.model_validate(r) for r in rows]
