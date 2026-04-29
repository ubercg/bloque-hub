"""CRM services: quote state machine, create_quote (SOFT_HOLD), PDF generation, contract send."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session, joinedload
from decimal import Decimal
from app.modules.pricing.services import get_quote_for_space
from weasyprint import HTML

from app.core.config import settings
from app.modules.crm.fea import FEAProviderMock, IFEAProvider, SendForSignatureResult
from app.modules.crm.fea.adapter import SignerInfo
from app.modules.crm.models import (
    Contract,
    ContractStatus,
    Lead,
    Quote,
    QuoteItem,
    QuoteStatus,
)
from app.modules.crm.schemas import QuoteItemCreate
from app.modules.inventory.services import (
    SlotNotAvailableError,
    apply_soft_hold_for_quote,
)

from app.modules.audit.service import append_audit_log

# Allowed transitions: from_status -> [to_statuses]
ALLOWED_QUOTE_TRANSITIONS: dict[QuoteStatus, list[QuoteStatus]] = {
    QuoteStatus.DRAFT: [QuoteStatus.DRAFT_PENDING_OPS, QuoteStatus.SENT],
    QuoteStatus.DRAFT_PENDING_OPS: [QuoteStatus.SENT],
    QuoteStatus.SENT: [QuoteStatus.APPROVED, QuoteStatus.DIGITAL_APPROVED],
    QuoteStatus.APPROVED: [],
    QuoteStatus.DIGITAL_APPROVED: [],
}


class InvalidQuoteTransitionError(Exception):
    """Raised when a quote status transition is not allowed."""


def _check_quote_transition(current: QuoteStatus, new: QuoteStatus) -> None:
    allowed = ALLOWED_QUOTE_TRANSITIONS.get(current, [])
    if new not in allowed:
        raise InvalidQuoteTransitionError(
            f"Transition from {current.value} to {new.value} is not allowed"
        )


def transition_quote_status(quote: Quote, new_status: QuoteStatus, db: Session) -> None:
    """Validate transition and update quote.status. Raises InvalidQuoteTransitionError if not allowed."""
    _check_quote_transition(quote.status, new_status)
    quote.status = new_status

    if new_status == QuoteStatus.DIGITAL_APPROVED:
        from app.modules.uma_rates.services import get_current_uma
        from app.modules.pricing.models import PricingRule
        from sqlalchemy import select
        
        try:
            uma = get_current_uma(quote.tenant_id, db=db)
            
            for item in quote.items:
                item.uma_snapshot = uma.value
                item.uma_snapshot_date = uma.effective_date
                
                # Freeze subtotal based on current price and discounts
                raw_price = item.precio
                discount = item.discount_amount or 0
                item.subtotal_frozen = float(raw_price) - float(discount)
                
        except Exception as e:
            # If no UMA rate exists, we still freeze the subtotal
            for item in quote.items:
                raw_price = item.precio
                discount = item.discount_amount or 0
                item.subtotal_frozen = float(raw_price) - float(discount)

    db.flush()


def create_quote(
    tenant_id: UUID,
    lead_id: UUID,
    items: list[QuoteItemCreate],
    discount_pct: float | None,
    discount_amount: float | None,
    discount_justification: str | None,
    db: Session,
) -> Quote:
    """
    Create a Quote (DRAFT) with QuoteItems and apply SOFT_HOLD on all slots atomically.
    Raises SlotNotAvailableError if any slot is not available; caller must rollback.
    """
    lead = db.get(Lead, lead_id)
    if lead is None or lead.tenant_id != tenant_id:
        raise ValueError("Lead not found or does not belong to tenant")

    # Calculamos el precio real por cada item usando pricing_rules si existen
    calculated_items = []
    total_decimal = Decimal("0.00")

    for it in items:
        # Convert fecha + hora to datetime
        start_time = datetime.combine(it.fecha, it.hora_inicio)
        end_time = datetime.combine(it.fecha, it.hora_fin)

        try:
            quote_calc = get_quote_for_space(
                db, tenant_id, it.space_id, start_time, end_time
            )
            calculated_price = quote_calc.total_price
        except (ValueError, Exception):
            # Fallback to provided price if no rule is found
            calculated_price = Decimal(str(it.precio))

        item_discount_amount = Decimal("0.00")
        item_discount_pct = Decimal("0.00")
        if it.discount_amount is not None and Decimal(str(it.discount_amount)) > 0:
            item_discount_amount = Decimal(str(it.discount_amount))
            if item_discount_amount > calculated_price:
                item_discount_amount = calculated_price
        elif it.discount_pct is not None and Decimal(str(it.discount_pct)) > 0:
            item_discount_pct = Decimal(str(it.discount_pct))
            if item_discount_pct > Decimal("100"):
                item_discount_pct = Decimal("100")
            item_discount_amount = (calculated_price * item_discount_pct / Decimal("100")).quantize(
                Decimal("0.01")
            )

        item_final_price = (calculated_price - item_discount_amount).quantize(Decimal("0.01"))
        calculated_items.append((it, float(item_final_price), float(item_discount_amount), float(item_discount_pct)))
        total_decimal += item_final_price

    quote_level_discount = Decimal("0.00")
    if discount_amount is not None and Decimal(str(discount_amount)) > 0:
        quote_level_discount = Decimal(str(discount_amount))
    elif discount_pct is not None and Decimal(str(discount_pct)) > 0:
        pct = Decimal(str(discount_pct))
        if pct > Decimal("100"):
            pct = Decimal("100")
        quote_level_discount = (total_decimal * pct / Decimal("100")).quantize(Decimal("0.01"))

    if quote_level_discount > total_decimal:
        quote_level_discount = total_decimal
    total_after_item = (total_decimal - quote_level_discount).quantize(Decimal("0.01"))
    total = float(total_after_item)

    quote = Quote(
        tenant_id=tenant_id,
        lead_id=lead_id,
        status=QuoteStatus.DRAFT,
        total=total,
        discount_pct=discount_pct,
        discount_amount=float(quote_level_discount) if quote_level_discount > 0 else None,
        discount_justification=discount_justification,
    )
    db.add(quote)
    db.flush()
    for i, (it, real_price, item_discount_amount_f, item_discount_pct_f) in enumerate(calculated_items):
        db.add(
            QuoteItem(
                quote_id=quote.id,
                space_id=it.space_id,
                fecha=it.fecha,
                hora_inicio=it.hora_inicio,
                hora_fin=it.hora_fin,
                precio=real_price,
                item_order=i,
                discount_amount=item_discount_amount_f if item_discount_amount_f > 0 else None,
                discount_percentage=item_discount_pct_f if item_discount_pct_f > 0 else None,
            )
        )
    db.flush()

    slots = [(it.space_id, it.fecha, it.hora_inicio, it.hora_fin) for it in items]
    apply_soft_hold_for_quote(quote.id, slots, tenant_id, db)
    return quote


def generate_quote_pdf(quote: Quote, db: Session) -> bytes:
    """Render quote (with lead and items) to HTML from template, then to PDF. Returns PDF bytes."""
    # Eager-load lead and items (and item.space for template)
    q = (
        db.query(Quote)
        .options(
            joinedload(Quote.lead),
            joinedload(Quote.items).joinedload(QuoteItem.space),
        )
        .filter(Quote.id == quote.id)
        .first()
    )
    if q is None:
        raise ValueError("Quote not found")
    quote = q

    templates_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(templates_dir)))
    template = env.get_template("quote_template.html")
    html = template.render(quote=quote, lead=quote.lead)
    pdf_bytes = HTML(string=html).write_pdf()
    return pdf_bytes


def generate_contract_pdf(quote: Quote, db: Session) -> bytes:
    """Render contract (quote + lead + items) from template to PDF. Returns PDF bytes."""
    q = (
        db.query(Quote)
        .options(
            joinedload(Quote.lead),
            joinedload(Quote.items).joinedload(QuoteItem.space),
        )
        .filter(Quote.id == quote.id)
        .first()
    )
    if q is None:
        raise ValueError("Quote not found")
    quote = q
    lead = quote.lead
    templates_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(templates_dir)))
    template = env.get_template("contract_template.html")
    html = template.render(quote=quote, lead=lead)
    pdf_bytes = HTML(string=html).write_pdf()
    return pdf_bytes


def _get_fea_provider() -> IFEAProvider:
    """Return FEA provider (mock or real) from config."""
    if settings.FEA_PROVIDER.lower() == "mock":
        return FEAProviderMock()
    return FEAProviderMock()


def send_contract_for_signature(
    quote: Quote,
    callback_url: str,
    db: Session,
) -> Contract:
    """
    Generate contract PDF, send to FEA provider (mock), create Contract with status SENT.
    Quote must be APPROVED; Lead must have email. Raises ValueError if not.
    """
    if quote.status != QuoteStatus.APPROVED:
        raise ValueError("Quote must be APPROVED to send contract")
    q = (
        db.query(Quote)
        .options(
            joinedload(Quote.lead), joinedload(Quote.items).joinedload(QuoteItem.space)
        )
        .filter(Quote.id == quote.id)
        .first()
    )
    if q is None:
        raise ValueError("Quote not found")
    quote = q
    lead = quote.lead
    if not lead or not lead.email:
        raise ValueError("Lead must have email to send contract")
    existing = db.query(Contract).filter(Contract.quote_id == quote.id).first()
    if existing:
        raise ValueError("Contract already exists for this quote")
    pdf_bytes = generate_contract_pdf(quote, db)
    signers = [SignerInfo(email=lead.email, name=lead.name)]
    provider = _get_fea_provider()
    result: SendForSignatureResult = provider.send_for_signature(
        pdf_bytes=pdf_bytes,
        signers=signers,
        title=f"Contrato cotización {quote.id}",
        callback_url=callback_url,
    )
    contract = Contract(
        tenant_id=quote.tenant_id,
        quote_id=quote.id,
        status=ContractStatus.SENT,
        provider_document_id=result.provider_document_id,
        fea_provider=settings.FEA_PROVIDER,
        sent_at=datetime.now(timezone.utc),
    )
    db.add(contract)
    db.flush()
    return contract
