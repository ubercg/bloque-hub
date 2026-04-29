from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import require_finance_or_admin, require_tenant
from app.modules.audit.service import append_audit_log
from app.modules.discounts.models import DiscountCode, DiscountCodeUsage
from app.modules.discounts.schemas import (
    DiscountCodeCreate,
    DiscountCodeRead,
    DiscountCodeUpdate,
    DiscountCodeUsageRead,
    DiscountValidateRequest,
    DiscountValidateResponse,
)
from app.modules.discounts.services import (
    DiscountValidationError,
    compute_discount_amount,
    discount_status,
    normalize_discount_code,
    validate_code_for_subtotal,
)


router = APIRouter(prefix="/api", tags=["discounts"])


@router.post("/discount-codes/validate", response_model=DiscountValidateResponse)
def validate_discount_code(
    body: DiscountValidateRequest,
    request: Request,
    db: Session = Depends(get_db),
    tenant_info: tuple[uuid.UUID, str | None] = Depends(require_tenant),
):
    tenant_id, _ = tenant_info
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    subtotal = Decimal(body.subtotal).quantize(Decimal("0.01"))
    code = normalize_discount_code(body.code)
    try:
        discount_code, discount_amount, total = validate_code_for_subtotal(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            code=code,
            subtotal=subtotal,
        )
        return DiscountValidateResponse(
            valid=True,
            code=discount_code.code,
            discount_code_id=discount_code.id,
            discount_type=discount_code.discount_type,  # type: ignore[arg-type]
            discount_value=Decimal(discount_code.discount_value),
            discount_amount=discount_amount,
            subtotal=subtotal,
            total=total,
            reason=None,
        )
    except DiscountValidationError as exc:
        return DiscountValidateResponse(
            valid=False,
            code=code,
            subtotal=subtotal,
            total=subtotal,
            discount_amount=Decimal("0.00"),
            reason=exc.reason,
        )


@router.post("/apply-discount-code", response_model=DiscountValidateResponse)
def apply_discount_code_preview(
    body: DiscountValidateRequest,
    request: Request,
    db: Session = Depends(get_db),
    tenant_info: tuple[uuid.UUID, str | None] = Depends(require_tenant),
):
    """Compat endpoint for quote preview; no usage is consumed here."""
    return validate_discount_code(body=body, request=request, db=db, tenant_info=tenant_info)


@router.get("/admin/discount-codes", response_model=list[DiscountCodeRead])
def list_discount_codes_admin(
    db: Session = Depends(get_db),
    tenant_info: tuple[uuid.UUID, str | None] = Depends(require_tenant),
    _: None = Depends(require_finance_or_admin),
):
    tenant_id, _ = tenant_info
    rows = db.query(DiscountCode).filter(DiscountCode.tenant_id == tenant_id).order_by(DiscountCode.created_at.desc()).all()
    out: list[DiscountCodeRead] = []
    for row in rows:
        out.append(
            DiscountCodeRead(
                id=row.id,
                tenant_id=row.tenant_id,
                code=row.code,
                discount_type=row.discount_type,  # type: ignore[arg-type]
                discount_value=Decimal(row.discount_value),
                min_subtotal=Decimal(row.min_subtotal) if row.min_subtotal is not None else None,
                max_uses=row.max_uses,
                used_count=row.used_count,
                active=row.active,
                expires_at=row.expires_at,
                single_use_per_user=row.single_use_per_user,
                description=row.description,
                created_by=row.created_by,
                created_at=row.created_at,
                updated_at=row.updated_at,
                status=discount_status(row),
            )
        )
    return out


@router.post("/admin/discount-codes", response_model=DiscountCodeRead, status_code=status.HTTP_201_CREATED)
def create_discount_code_admin(
    body: DiscountCodeCreate,
    request: Request,
    db: Session = Depends(get_db),
    tenant_info: tuple[uuid.UUID, str | None] = Depends(require_tenant),
    _: None = Depends(require_finance_or_admin),
):
    tenant_id, _ = tenant_info
    code = normalize_discount_code(body.code)
    exists = db.execute(
        select(DiscountCode.id).where(
            DiscountCode.tenant_id == tenant_id,
            func.upper(DiscountCode.code) == code,
        ).limit(1)
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=409, detail="DISCOUNT_CODE_ALREADY_EXISTS")

    user_id = getattr(request.state, "user_id", None)
    row = DiscountCode(
        tenant_id=tenant_id,
        code=code,
        discount_type=body.discount_type,
        discount_value=body.discount_value,
        min_subtotal=body.min_subtotal,
        max_uses=body.max_uses,
        used_count=0,
        active=body.active,
        expires_at=body.expires_at,
        single_use_per_user=body.single_use_per_user,
        description=body.description,
        created_by=user_id,
    )
    db.add(row)
    db.flush()

    append_audit_log(
        db=db,
        tenant_id=tenant_id,
        tabla="discount_codes",
        registro_id=row.id,
        accion="CREATE",
        campo_modificado="*",
        valor_anterior=None,
        valor_nuevo={
            "code": row.code,
            "discount_type": row.discount_type,
            "discount_value": str(row.discount_value),
            "min_subtotal": str(row.min_subtotal) if row.min_subtotal is not None else None,
            "max_uses": row.max_uses,
            "active": row.active,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "single_use_per_user": row.single_use_per_user,
        },
        actor_id=user_id,
        actor_ip=request.client.host if request.client else None,
        actor_user_agent=request.headers.get("User-Agent"),
    )
    db.commit()
    db.refresh(row)

    return DiscountCodeRead(
        id=row.id,
        tenant_id=row.tenant_id,
        code=row.code,
        discount_type=row.discount_type,  # type: ignore[arg-type]
        discount_value=Decimal(row.discount_value),
        min_subtotal=Decimal(row.min_subtotal) if row.min_subtotal is not None else None,
        max_uses=row.max_uses,
        used_count=row.used_count,
        active=row.active,
        expires_at=row.expires_at,
        single_use_per_user=row.single_use_per_user,
        description=row.description,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        status=discount_status(row),
    )


@router.patch("/admin/discount-codes/{discount_code_id}", response_model=DiscountCodeRead)
def update_discount_code_admin(
    discount_code_id: uuid.UUID,
    body: DiscountCodeUpdate,
    request: Request,
    db: Session = Depends(get_db),
    tenant_info: tuple[uuid.UUID, str | None] = Depends(require_tenant),
    _: None = Depends(require_finance_or_admin),
):
    tenant_id, _ = tenant_info
    row = db.query(DiscountCode).filter(
        DiscountCode.id == discount_code_id,
        DiscountCode.tenant_id == tenant_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="DISCOUNT_CODE_NOT_FOUND")

    before = {
        "discount_value": str(row.discount_value),
        "min_subtotal": str(row.min_subtotal) if row.min_subtotal is not None else None,
        "max_uses": row.max_uses,
        "active": row.active,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "single_use_per_user": row.single_use_per_user,
        "description": row.description,
    }
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(row, key, value)
    db.flush()

    user_id = getattr(request.state, "user_id", None)
    append_audit_log(
        db=db,
        tenant_id=tenant_id,
        tabla="discount_codes",
        registro_id=row.id,
        accion="UPDATE",
        campo_modificado="*",
        valor_anterior=before,
        valor_nuevo={
            "discount_value": str(row.discount_value),
            "min_subtotal": str(row.min_subtotal) if row.min_subtotal is not None else None,
            "max_uses": row.max_uses,
            "active": row.active,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "single_use_per_user": row.single_use_per_user,
            "description": row.description,
        },
        actor_id=user_id,
        actor_ip=request.client.host if request.client else None,
        actor_user_agent=request.headers.get("User-Agent"),
    )
    db.commit()
    db.refresh(row)

    return DiscountCodeRead(
        id=row.id,
        tenant_id=row.tenant_id,
        code=row.code,
        discount_type=row.discount_type,  # type: ignore[arg-type]
        discount_value=Decimal(row.discount_value),
        min_subtotal=Decimal(row.min_subtotal) if row.min_subtotal is not None else None,
        max_uses=row.max_uses,
        used_count=row.used_count,
        active=row.active,
        expires_at=row.expires_at,
        single_use_per_user=row.single_use_per_user,
        description=row.description,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        status=discount_status(row),
    )


@router.get("/admin/discount-codes/{discount_code_id}/usages", response_model=list[DiscountCodeUsageRead])
def list_discount_code_usages_admin(
    discount_code_id: uuid.UUID,
    db: Session = Depends(get_db),
    tenant_info: tuple[uuid.UUID, str | None] = Depends(require_tenant),
    _: None = Depends(require_finance_or_admin),
):
    tenant_id, _ = tenant_info
    rows = (
        db.query(DiscountCodeUsage)
        .filter(
            DiscountCodeUsage.tenant_id == tenant_id,
            DiscountCodeUsage.discount_code_id == discount_code_id,
        )
        .order_by(DiscountCodeUsage.used_at.desc())
        .all()
    )
    return rows
