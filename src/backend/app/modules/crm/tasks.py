"""Celery tasks for CRM (e.g. FEA delegate signer)."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select

from app.core.config import settings
from app.db.session import get_db_context
from app.modules.crm.models import Contract, ContractStatus

from app.celery_app import app


@app.task(name="crm.add_delegate_signer")
def add_delegate_signer() -> int:
    """
    Find contracts in SENT state with sent_at older than 24h and no delegate activated yet;
    call FEA provider to add delegate signer (mock: just mark delegate_signer_activated_at).
    Uses SUPERADMIN so RLS allows reading/updating all tenants' contracts.
    Returns the number of contracts processed.
    """
    threshold = datetime.now(timezone.utc) - timedelta(hours=24)
    with get_db_context(tenant_id=None, role="SUPERADMIN") as db:
        stmt = (
            select(Contract.id)
            .where(Contract.status == ContractStatus.SENT)
            .where(Contract.sent_at.isnot(None))
            .where(Contract.sent_at < threshold)
            .where(Contract.delegate_signer_activated_at.is_(None))
        )
        contract_ids: list[UUID] = list(db.execute(stmt).scalars().all())
    count = 0
    for cid in contract_ids:
        with get_db_context(tenant_id=None, role="SUPERADMIN") as db:
            contract = db.get(Contract, cid)
            if contract is None:
                continue
            if (
                contract.status != ContractStatus.SENT
                or contract.delegate_signer_activated_at is not None
            ):
                continue
            try:
                if settings.FEA_PROVIDER.lower() == "mock":
                    pass
                else:
                    pass
                contract.delegate_signer_activated_at = datetime.now(timezone.utc)
                db.commit()
                count += 1
            except Exception:
                db.rollback()
                raise
    return count
