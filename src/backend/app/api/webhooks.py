"""Webhook endpoints (public, no JWT)."""

import hmac
import hashlib
import json
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Request, status
from fastapi.exceptions import HTTPException
from sqlalchemy.orm import joinedload

from app.core.config import settings
from app.db.session import get_db_context
from app.modules.crm.models import Contract, ContractStatus
from app.modules.crm.services import generate_contract_pdf
from app.modules.fulfillment.services import create_os_for_contract

router = APIRouter(prefix="/api", tags=["webhooks"])


def _verify_hmac(body: bytes, signature_header: str | None) -> bool:
    if settings.FEA_SKIP_HMAC_IN_TESTS:
        return True
    if not signature_header:
        return False
    expected = hmac.new(
        settings.FEA_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature_header, f"sha256={expected}")


@router.post("/webhooks/fea", status_code=status.HTTP_204_NO_CONTENT)
async def fea_webhook(request: Request) -> None:
    """
    Receive FEA provider webhook (signed, rejected, expired).
    Validate HMAC if not skipped (FEA_SKIP_HMAC_IN_TESTS). Idempotent.
    """
    body = await request.body()
    signature = request.headers.get("X-Webhook-Signature") or request.headers.get("X-Signature")
    if not _verify_hmac(body, signature):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")
    provider_document_id = data.get("provider_document_id") or data.get("document_id")
    event = (data.get("event") or data.get("status") or "").lower()
    if not provider_document_id or event not in ("signed", "rejected", "expired"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing provider_document_id or invalid event",
        )
    with get_db_context(tenant_id=None, role="SUPERADMIN") as db:
        contract = (
            db.query(Contract)
            .options(joinedload(Contract.quote))
            .filter(Contract.provider_document_id == str(provider_document_id))
            .first()
        )
        if not contract:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
        if contract.status in (ContractStatus.SIGNED, ContractStatus.REJECTED, ContractStatus.EXPIRED):
            return
        if event == "signed":
            contract.status = ContractStatus.SIGNED
            storage_path = Path(settings.CONTRACTS_STORAGE_PATH)
            storage_path.mkdir(parents=True, exist_ok=True)
            filename = f"{contract.id}_signed.pdf"
            file_path = storage_path / filename
            pdf_url_from_payload = data.get("signed_document_url")
            if pdf_url_from_payload:
                try:
                    import urllib.request
                    with urllib.request.urlopen(pdf_url_from_payload) as resp:
                        file_path.write_bytes(resp.read())
                except Exception:
                    pass
            if not file_path.exists():
                pdf_bytes = generate_contract_pdf(contract.quote, db)
                file_path.write_bytes(pdf_bytes)
            contract.signed_document_url = filename
            create_os_for_contract(contract, db)
        elif event == "rejected":
            contract.status = ContractStatus.REJECTED
        else:
            contract.status = ContractStatus.EXPIRED
        db.commit()
