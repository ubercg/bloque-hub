import hmac
import hashlib
import uuid
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.modules.payments.models import PaymentReference
from app.modules.payments.schemas import PaymentReferenceCreate, SPEIWebhookPayload
from app.core.config import settings
from app.core.exceptions import DomainException

def generate_spei_reference(db: Session, tenant_id: uuid.UUID, data: PaymentReferenceCreate) -> PaymentReference:
    # Generate a unique reference code (e.g., prefix + reservation short + random)
    raw_ref = f"{data.reservation_id.hex[:8]}-{uuid.uuid4().hex[:6]}".upper()
    
    # Sign the reference with HMAC-SHA256 for integrity
    signature = hmac.new(
        settings.SPEI_SECRET_KEY.encode(),
        raw_ref.encode(),
        hashlib.sha256
    ).hexdigest()[:10].upper()
    
    reference_code = f"CIE-{raw_ref}-{signature}"
    
    payment_ref = PaymentReference(
        tenant_id=tenant_id,
        reservation_id=data.reservation_id,
        reference_code=reference_code,
        amount=data.amount,
        status="PENDING"
    )
    db.add(payment_ref)
    db.commit()
    db.refresh(payment_ref)
    return payment_ref

def process_spei_webhook(db: Session, payload: SPEIWebhookPayload) -> None:
    # Find the reference (Webhook might not have tenant context, so we query globally but safely)
    stmt = select(PaymentReference).where(PaymentReference.reference_code == payload.reference_code)
    payment_ref = db.execute(stmt).scalar_one_or_none()
    
    if not payment_ref:
        raise DomainException(f"Payment reference {payload.reference_code} not found")
        
    if payment_ref.status == "PAID":
        return  # Idempotent
        
    if payload.amount_paid < payment_ref.amount:
        raise DomainException("Insufficient amount paid")
        
    payment_ref.status = "PAID"
    payment_ref.paid_at = payload.payment_date
    
    # Here we would also trigger reservation reconciliation
    # e.g., update_reservation_status(db, payment_ref.reservation_id, "CONFIRMED")
    
    db.commit()