"""Pydantic schemas for reservation KYC documents API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class DocumentItemStatus(BaseModel):
    type: str
    label: str
    status: Literal["OK", "MISSING", "REQUIRES_UPDATE"]
    document_id: uuid.UUID | None = None


class CompletenessResponse(BaseModel):
    required: list[DocumentItemStatus]
    optional: list[DocumentItemStatus]
    is_complete: bool


class ReservationDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    group_event_id: uuid.UUID
    document_type_id: uuid.UUID
    document_type_code: str
    storage_key: str
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    status: str
    created_at: datetime
    superseded_by_id: uuid.UUID | None = None


class DocumentTypeDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    label: str
    required: bool
    requires_condition: str
    mime_rules: list[str]
    active: bool
    sort_order: int


class UploadResponse(BaseModel):
    document: ReservationDocumentRead
