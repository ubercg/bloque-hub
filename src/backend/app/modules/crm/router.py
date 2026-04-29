"""REST API for CRM: leads and quotes."""

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.exceptions import HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.dependencies.auth import require_tenant, require_commercial_or_admin
from app.modules.crm.models import Contract, ContractStatus, Lead, Quote
from app.modules.crm.schemas import (
    LeadCreate,
    LeadRead,
    QuoteCreate,
    QuoteRead,
    QuoteStatusUpdate,
)
from app.modules.crm.schemas import ContractRead
from app.modules.crm.services import (
    InvalidQuoteTransitionError,
    create_quote,
    generate_quote_pdf,
    send_contract_for_signature,
    transition_quote_status,
)
from app.modules.inventory.services import SlotNotAvailableError

router = APIRouter(prefix="/api", tags=["crm"])


def _get_lead_or_404(lead_id: UUID, tenant_id: UUID, db: Session) -> Lead:
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.tenant_id == tenant_id).first()
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return lead


def _get_quote_or_404(quote_id: UUID, tenant_id: UUID, db: Session) -> Quote:
    quote = db.query(Quote).filter(Quote.id == quote_id, Quote.tenant_id == tenant_id).first()
    if quote is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found")
    return quote


def _get_contract_or_404(contract_id: UUID, tenant_id: UUID, db: Session) -> Contract:
    contract = (
        db.query(Contract).filter(Contract.id == contract_id, Contract.tenant_id == tenant_id).first()
    )
    if contract is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    return contract


# ----- Leads -----


@router.post("/leads", response_model=LeadRead, status_code=status.HTTP_201_CREATED)
def post_lead(
    request: Request,
    body: LeadCreate,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Create a lead."""
    tenant_id = request.state.tenant_id
    lead = Lead(tenant_id=tenant_id, **body.model_dump())
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


@router.get("/leads", response_model=list[LeadRead])
def list_leads(
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """List leads for the current tenant."""
    # RLS filters by tenant when app.current_tenant_id is set
    return db.query(Lead).all()


@router.get("/leads/{lead_id}", response_model=LeadRead)
def get_lead(
    request: Request,
    lead_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Get one lead by id."""
    tenant_id = request.state.tenant_id
    return _get_lead_or_404(lead_id, tenant_id, db)


# ----- Quotes -----


@router.post("/quotes", response_model=QuoteRead, status_code=status.HTTP_201_CREATED)
def post_quote(
    request: Request,
    body: QuoteCreate,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Create a quote (DRAFT) and apply SOFT_HOLD on selected slots. Fails if any slot is unavailable."""
    tenant_id = request.state.tenant_id
    try:
        quote = create_quote(
            tenant_id=tenant_id,
            lead_id=body.lead_id,
            items=body.items,
            discount_pct=body.discount_pct,
            discount_amount=body.discount_amount,
            discount_justification=body.discount_justification,
            db=db,
        )
        db.commit()
        db.refresh(quote)
        # Load items for response
        db.refresh(quote)
        return quote
    except SlotNotAvailableError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SLOT_NO_DISPONIBLE",
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/quotes", response_model=list[QuoteRead])
def list_quotes(
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """List quotes for the current tenant."""
    return db.query(Quote).all()


@router.get("/quotes/{quote_id}", response_model=QuoteRead)
def get_quote(
    request: Request,
    quote_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Get one quote by id."""
    tenant_id = request.state.tenant_id
    return _get_quote_or_404(quote_id, tenant_id, db)


@router.patch("/quotes/{quote_id}/status", status_code=status.HTTP_204_NO_CONTENT)
def patch_quote_status(
    request: Request,
    quote_id: UUID,
    body: QuoteStatusUpdate,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
    __: None = Depends(require_commercial_or_admin),
):
    """Update quote status. Requires COMMERCIAL, FINANCE or SUPERADMIN."""
    tenant_id = request.state.tenant_id
    quote = _get_quote_or_404(quote_id, tenant_id, db)
    try:
        transition_quote_status(quote, body.status, db)
        db.commit()
    except InvalidQuoteTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/quotes/{quote_id}/send-contract",
    response_model=ContractRead,
    status_code=status.HTTP_201_CREATED,
)
def post_quote_send_contract(
    request: Request,
    quote_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
    __: None = Depends(require_commercial_or_admin),
):
    """Send contract for signature (FEA). Quote must be APPROVED. Requires COMMERCIAL, FINANCE or SUPERADMIN."""
    tenant_id = request.state.tenant_id
    quote = _get_quote_or_404(quote_id, tenant_id, db)
    base_url = str(request.base_url).rstrip("/")
    callback_url = f"{base_url}/api/webhooks/fea"
    try:
        contract = send_contract_for_signature(quote, callback_url=callback_url, db=db)
        db.commit()
        db.refresh(contract)
        return contract
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/quotes/{quote_id}/contract", response_model=ContractRead)
def get_quote_contract(
    request: Request,
    quote_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Get contract for a quote if it exists."""
    tenant_id = request.state.tenant_id
    _get_quote_or_404(quote_id, tenant_id, db)
    contract = (
        db.query(Contract).filter(Contract.quote_id == quote_id, Contract.tenant_id == tenant_id).first()
    )
    if contract is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    return contract


@router.get("/contracts/{contract_id}/signed-pdf")
def get_contract_signed_pdf(
    request: Request,
    contract_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Download signed contract PDF (filesystem). Contract must be SIGNED."""
    tenant_id = request.state.tenant_id
    contract = _get_contract_or_404(contract_id, tenant_id, db)
    if contract.status != ContractStatus.SIGNED or not contract.signed_document_url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signed document not available")
    path = Path(settings.CONTRACTS_STORAGE_PATH) / contract.signed_document_url
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"contrato-{contract_id}-firmado.pdf",
    )


@router.get("/quotes/{quote_id}/download")
def get_quote_download(
    request: Request,
    quote_id: UUID,
    db: Session = Depends(get_db),
    _: tuple[UUID, str | None] = Depends(require_tenant),
    __: None = Depends(require_commercial_or_admin),
):
    """Download quote as PDF. Requires COMMERCIAL, FINANCE or SUPERADMIN."""
    tenant_id = request.state.tenant_id
    quote = _get_quote_or_404(quote_id, tenant_id, db)
    try:
        pdf_bytes = generate_quote_pdf(quote, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="cotizacion-{quote_id}.pdf"',
        },
    )
