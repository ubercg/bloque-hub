"""Pydantic schemas for fulfillment."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.fulfillment.models import (
    EvidenceStatus,
    MasterServiceOrderStatus,
    ServiceOrderItemStatus,
)


class ServiceOrderItemRead(BaseModel):
    id: UUID
    checklist_id: UUID
    title: str
    item_order: int
    is_critical: bool = False
    status: ServiceOrderItemStatus
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class ChecklistRead(BaseModel):
    id: UUID
    master_service_order_id: UUID
    name: str
    item_order: int
    items: list[ServiceOrderItemRead] = []

    model_config = {"from_attributes": True}


class MasterServiceOrderRead(BaseModel):
    id: UUID
    tenant_id: UUID
    reservation_id: UUID | None
    contract_id: UUID | None
    status: MasterServiceOrderStatus
    created_at: datetime
    updated_at: datetime
    checklists: list[ChecklistRead] = []

    model_config = {"from_attributes": True}


class ServiceOrderIdRead(BaseModel):
    """Minimal response for staff to get order id by reservation."""
    id: UUID


class MasterServiceOrderStatusUpdate(BaseModel):
    status: MasterServiceOrderStatus


class ServiceOrderItemStatusUpdate(BaseModel):
    status: ServiceOrderItemStatus


class EvidenceRequirementRead(BaseModel):
    id: UUID
    tenant_id: UUID
    master_service_order_id: UUID
    tipo_documento: str
    estado: EvidenceStatus
    filename: str | None
    file_size_bytes: int | None
    uploaded_at: datetime | None
    plazo_vence_at: datetime
    revisado_at: datetime | None
    motivo_rechazo: str | None
    intentos_carga: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EvidenceRequirementReview(BaseModel):
    """Body for Operations to approve or reject evidence."""

    estado: EvidenceStatus = Field(..., description="APROBADO or RECHAZADO")
    motivo_rechazo: str | None = Field(None, max_length=2000)


class ReadinessDetail(BaseModel):
    pending_critical_items: list[dict] = []
    pending_evidence: list[dict] = []


class ReadinessRead(BaseModel):
    is_ready: bool
    checklist_pct: float
    evidence_complete: bool
    details: ReadinessDetail = Field(default_factory=ReadinessDetail)
