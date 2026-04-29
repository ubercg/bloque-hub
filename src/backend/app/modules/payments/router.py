import uuid
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.dependencies.auth import require_tenant
from app.modules.payments.schemas import PaymentReferenceCreate, PaymentReferenceResponse, SPEIWebhookPayload
from app.modules.payments.services import generate_spei_reference, process_spei_webhook
import hmac
import hashlib
from app.core.config import settings
from app.core.exceptions import DomainException

router = APIRouter(prefix="/api/payments", tags=["payments"])

@router.post("/spei/reference", response_model=PaymentReferenceResponse, status_code=status.HTTP_201_CREATED)
def create_spei_reference(
    data: PaymentReferenceCreate,
    db: Session = Depends(get_db),
    tenant_role: tuple = Depends(require_tenant)
):
    return generate_spei_reference(db, tenant_role[0], data)

@router.post("/webhooks/spei", status_code=status.HTTP_204_NO_CONTENT)
async def spei_webhook(
    request: Request,
    payload: SPEIWebhookPayload,
    db: Session = Depends(get_db)
):
    body = await request.body()
    signature = request.headers.get("X-SPEI-Signature")
    
    if not signature:
        raise DomainException("Missing signature")
        
    expected = hmac.new(
        settings.SPEI_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(signature, expected):
        raise DomainException("Invalid signature")
        
    process_spei_webhook(db, payload)