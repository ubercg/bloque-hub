from sqlalchemy.orm import Session
from sqlalchemy import text
from uuid import UUID
from datetime import date
from typing import Optional
from .schemas import (
    KR23MetricResponse,
    KR24MetricResponse,
    KR25MetricResponse,
    KR27MetricResponse,
    DashboardMetricsResponse
)

def build_date_filter(start_date: Optional[date], end_date: Optional[date], column: str) -> str:
    filter_sql = ""
    if start_date:
        filter_sql += f" AND {column} >= :start_date"
    if end_date:
        filter_sql += f" AND {column} <= :end_date"
    return filter_sql

def get_kr23_metrics(db: Session, tenant_id: UUID, start_date: Optional[date] = None, end_date: Optional[date] = None) -> KR23MetricResponse:
    # KR-23: Descuento con justificación + audit_log
    date_filter = build_date_filter(start_date, end_date, "created_at")
    query = text(f"""
        SELECT 
            COUNT(*) as total_discounts,
            SUM(CASE WHEN justification IS NOT NULL THEN 1 ELSE 0 END) as justified_discounts
        FROM quotes
        WHERE tenant_id = :tenant_id AND discount_amount > 0 {date_filter}
    """)
    params = {"tenant_id": tenant_id}
    if start_date: params["start_date"] = start_date
    if end_date: params["end_date"] = end_date
    
    result = db.execute(query, params).fetchone()
    
    total = result.total_discounts if result and result.total_discounts else 0
    justified = result.justified_discounts if result and result.justified_discounts else 0
    rate = (justified / total * 100) if total > 0 else 100.0
    
    return KR23MetricResponse(
        total_discounts=total,
        justified_discounts=justified,
        justification_rate=rate
    )

def get_kr24_metrics(db: Session, tenant_id: UUID, start_date: Optional[date] = None, end_date: Optional[date] = None) -> KR24MetricResponse:
    # KR-24: Invariancia total MXN vs snapshot
    date_filter = build_date_filter(start_date, end_date, "created_at")
    query = text(f"""
        SELECT 
            COUNT(*) as total_snapshots,
            SUM(CASE WHEN current_total_mxn = snapshot_total_mxn THEN 1 ELSE 0 END) as invariant_snapshots
        FROM quote_snapshots
        WHERE tenant_id = :tenant_id {date_filter}
    """)
    params = {"tenant_id": tenant_id}
    if start_date: params["start_date"] = start_date
    if end_date: params["end_date"] = end_date

    result = db.execute(query, params).fetchone()
    
    total = result.total_snapshots if result and result.total_snapshots else 0
    invariant = result.invariant_snapshots if result and result.invariant_snapshots else 0
    rate = (invariant / total * 100) if total > 0 else 100.0
    
    return KR24MetricResponse(
        total_snapshots=total,
        invariant_snapshots=invariant,
        invariance_rate=rate
    )

def get_kr25_metrics(db: Session, tenant_id: UUID, start_date: Optional[date] = None, end_date: Optional[date] = None) -> KR25MetricResponse:
    # KR-25: Precisión pricing híbrido
    date_filter = build_date_filter(start_date, end_date, "created_at")
    query = text(f"""
        SELECT 
            COUNT(*) as total_hybrid,
            SUM(CASE WHEN is_accurate = true THEN 1 ELSE 0 END) as accurate_hybrid
        FROM hybrid_pricing_logs
        WHERE tenant_id = :tenant_id {date_filter}
    """)
    params = {"tenant_id": tenant_id}
    if start_date: params["start_date"] = start_date
    if end_date: params["end_date"] = end_date

    result = db.execute(query, params).fetchone()
    
    total = result.total_hybrid if result and result.total_hybrid else 0
    accurate = result.accurate_hybrid if result and result.accurate_hybrid else 0
    rate = (accurate / total * 100) if total > 0 else 100.0
    
    return KR25MetricResponse(
        total_hybrid_quotes=total,
        accurate_hybrid_quotes=accurate,
        precision_rate=rate
    )

def get_kr27_metrics(db: Session, tenant_id: UUID, start_date: Optional[date] = None, end_date: Optional[date] = None) -> KR27MetricResponse:
    # KR-27: Gating READY con checklist de montaje
    date_filter = build_date_filter(start_date, end_date, "transitioned_at")
    query = text(f"""
        SELECT 
            COUNT(*) as total_ready,
            SUM(CASE WHEN has_checklist = true THEN 1 ELSE 0 END) as with_checklist
        FROM booking_status_transitions
        WHERE tenant_id = :tenant_id AND to_status = 'READY' {date_filter}
    """)
    params = {"tenant_id": tenant_id}
    if start_date: params["start_date"] = start_date
    if end_date: params["end_date"] = end_date

    result = db.execute(query, params).fetchone()
    
    total = result.total_ready if result and result.total_ready else 0
    with_checklist = result.with_checklist if result and result.with_checklist else 0
    rate = (with_checklist / total * 100) if total > 0 else 100.0
    
    return KR27MetricResponse(
        total_ready_transitions=total,
        transitions_with_checklist=with_checklist,
        compliance_rate=rate
    )

def get_dashboard_metrics(db: Session, tenant_id: UUID, start_date: Optional[date] = None, end_date: Optional[date] = None) -> DashboardMetricsResponse:
    return DashboardMetricsResponse(
        kr23=get_kr23_metrics(db, tenant_id, start_date, end_date),
        kr24=get_kr24_metrics(db, tenant_id, start_date, end_date),
        kr25=get_kr25_metrics(db, tenant_id, start_date, end_date),
        kr27=get_kr27_metrics(db, tenant_id, start_date, end_date)
    )
