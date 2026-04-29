import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.dependencies.auth import require_tenant, require_commercial_or_admin
from app.modules.pricing.models import PricingRule
from app.modules.pricing.schemas import PricingRuleCreate, PricingRuleUpdate, PricingRuleResponse, QuoteCalculationRequest, QuoteCalculationResponse
from app.modules.pricing.services import create_pricing_rule, update_pricing_rule, get_pricing_rule_by_space, get_quote_for_space

router = APIRouter(prefix="/api", tags=["pricing"])

@router.get("/pricing-rules", response_model=List[PricingRuleResponse])
def list_pricing_rules(
    db: Session = Depends(get_db),
    tenant_info: tuple[uuid.UUID, str] = Depends(require_tenant)
):
    tenant_id, _ = tenant_info
    return db.query(PricingRule).filter(PricingRule.tenant_id == tenant_id).all()

@router.post("/pricing-rules", response_model=PricingRuleResponse, status_code=status.HTTP_201_CREATED)
def add_pricing_rule(
    rule: PricingRuleCreate,
    db: Session = Depends(get_db),
    tenant_info: tuple[uuid.UUID, str] = Depends(require_tenant),
    _: None = Depends(require_commercial_or_admin),
):
    tenant_id, _ = tenant_info
    existing = get_pricing_rule_by_space(db, tenant_id, rule.space_id)
    if existing:
        raise HTTPException(status_code=400, detail="Pricing rule already exists for this space on this date")
    try:
        created = create_pricing_rule(db, tenant_id, rule)
        db.commit()
        db.refresh(created)
        return created
    except Exception:
        db.rollback()
        raise

@router.put("/pricing-rules/{space_id}", response_model=PricingRuleResponse)
def modify_pricing_rule(
    space_id: uuid.UUID,
    rule: PricingRuleUpdate,
    db: Session = Depends(get_db),
    tenant_info: tuple[uuid.UUID, str] = Depends(require_tenant),
    _: None = Depends(require_commercial_or_admin),
):
    tenant_id, _ = tenant_info
    try:
        updated = update_pricing_rule(db, tenant_id, space_id, rule)
        if not updated:
            raise HTTPException(status_code=404, detail="Pricing rule not found")
        db.commit()
        db.refresh(updated)
        return updated
    except Exception:
        db.rollback()
        raise

@router.get("/pricing-rules/{space_id}", response_model=PricingRuleResponse)
def fetch_pricing_rule(
    space_id: uuid.UUID,
    db: Session = Depends(get_db),
    tenant_info: tuple[uuid.UUID, str] = Depends(require_tenant)
):
    tenant_id, _ = tenant_info
    rule = get_pricing_rule_by_space(db, tenant_id, space_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Pricing rule not found")
    return rule

@router.post("/quotes/calculate", response_model=QuoteCalculationResponse)
def calculate_quote(
    req: QuoteCalculationRequest,
    db: Session = Depends(get_db),
    tenant_info: tuple[uuid.UUID, str] = Depends(require_tenant)
):
    tenant_id, _ = tenant_info
    try:
        return get_quote_for_space(db, tenant_id, req.space_id, req.target_date, req.duration_hours)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
