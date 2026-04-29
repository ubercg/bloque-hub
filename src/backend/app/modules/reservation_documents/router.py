"""Endpoints KYC por group_event_id (borradores versionados)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.permissions import STAFF_ROLES
from app.db.session import get_db
from app.dependencies.auth import require_tenant
from app.modules.reservation_documents.schemas import (
    CompletenessResponse,
    DocumentTypeDefinitionRead,
    ReservationDocumentRead,
    UploadResponse,
)
from app.modules.reservation_documents.services import (
    build_completeness,
    group_belongs_to_tenant,
    list_active_documents,
    list_documents_with_history,
    list_global_definitions,
    read_file_bytes,
    reservation_document_to_read,
    upload_document_version,
    verify_customer_owns_group,
)

router = APIRouter(prefix="/api", tags=["reservation-documents"])


def _assert_group_documents_access(
    request: Request,
    db: Session,
    tenant_id: UUID,
    group_event_id: UUID,
) -> None:
    """CUSTOMER: solo su grupo. Staff del tenant: mismo tenant y grupo válido."""
    uid = getattr(request.state, "user_id", None)
    if uid is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    role = getattr(request.state, "role", None)
    if role in STAFF_ROLES:
        if not group_belongs_to_tenant(db, tenant_id=tenant_id, group_event_id=group_event_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo no encontrado")
        return
    if not verify_customer_owns_group(
        db, tenant_id=tenant_id, group_event_id=group_event_id, user_id=uid
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grupo no encontrado")


def _err_map(exc: ValueError) -> tuple[int, str]:
    code = str(exc.args[0]) if exc.args else "ERROR"
    mapping: dict[str, tuple[int, str]] = {
        "GROUP_NOT_FOUND": (status.HTTP_404_NOT_FOUND, "Grupo de reserva no encontrado."),
        "FORBIDDEN": (status.HTTP_403_FORBIDDEN, "No tienes acceso a este grupo."),
        "INVALID_STATE": (
            status.HTTP_400_BAD_REQUEST,
            "Solo se pueden subir documentos mientras la reserva está pendiente de comprobante o en espera de pago.",
        ),
        "UNKNOWN_DOCUMENT_TYPE": (status.HTTP_400_BAD_REQUEST, "Tipo de documento no válido."),
        "INVALID_MIME": (status.HTTP_400_BAD_REQUEST, "Tipo de archivo no permitido para este documento."),
        "DISCOUNT_DOC_NOT_APPLICABLE": (
            status.HTTP_400_BAD_REQUEST,
            "Este documento solo aplica cuando hay un código de descuento aplicado.",
        ),
        "FILE_TOO_LARGE": (status.HTTP_400_BAD_REQUEST, "El archivo excede el tamaño máximo permitido."),
        "FILE_EMPTY": (status.HTTP_400_BAD_REQUEST, "El archivo está vacío."),
        "GROUP_QUOTA_EXCEEDED": (
            status.HTTP_400_BAD_REQUEST,
            "Se excedió el límite total de almacenamiento para este evento.",
        ),
    }
    return mapping.get(code, (status.HTTP_400_BAD_REQUEST, code))


@router.get("/document-type-definitions", response_model=list[DocumentTypeDefinitionRead])
def get_document_type_definitions(
    db: Session = Depends(get_db),
    tenant_data: tuple[UUID, str | None] = Depends(require_tenant),
):
    """Definiciones globales (y futuras por tenant) para armar la UI de carga."""
    _tid, _role = tenant_data
    defs = list_global_definitions(db)
    out: list[DocumentTypeDefinitionRead] = []
    for d in defs:
        mr = d.mime_rules if isinstance(d.mime_rules, list) else []
        out.append(
            DocumentTypeDefinitionRead(
                id=d.id,
                code=d.code,
                label=d.label,
                required=d.required,
                requires_condition=d.requires_condition,
                mime_rules=[str(x) for x in mr],
                active=d.active,
                sort_order=d.sort_order,
            )
        )
    return out


@router.get(
    "/group-events/{group_event_id}/documents/completeness",
    response_model=CompletenessResponse,
)
def get_documents_completeness(
    group_event_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    tenant_data: tuple[UUID, str | None] = Depends(require_tenant),
):
    tenant_id, _role = tenant_data
    _assert_group_documents_access(request, db, tenant_id, group_event_id)
    return build_completeness(db, tenant_id=tenant_id, group_event_id=group_event_id)


@router.get("/group-events/{group_event_id}/documents", response_model=list[ReservationDocumentRead])
def get_group_documents(
    group_event_id: UUID,
    request: Request,
    include_history: bool = Query(False, description="Incluir versiones SUPERSEDED"),
    db: Session = Depends(get_db),
    tenant_data: tuple[UUID, str | None] = Depends(require_tenant),
):
    """CUSTOMER: solo su grupo. Staff del tenant: listado para inspección (misma regla que completeness y /file)."""
    tenant_id, _role = tenant_data
    _assert_group_documents_access(request, db, tenant_id, group_event_id)
    if include_history:
        return list_documents_with_history(db, tenant_id=tenant_id, group_event_id=group_event_id)
    return list_active_documents(db, tenant_id=tenant_id, group_event_id=group_event_id)


@router.post(
    "/group-events/{group_event_id}/documents",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_group_document(
    request: Request,
    group_event_id: UUID,
    document_type_id: UUID = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    tenant_data: tuple[UUID, str | None] = Depends(require_tenant),
):
    tenant_id, _role = tenant_data
    uid = getattr(request.state, "user_id", None)
    if uid is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    content = file.file.read()
    mime = file.content_type or "application/octet-stream"
    name = file.filename or "upload"
    try:
        doc = upload_document_version(
            db,
            tenant_id=tenant_id,
            group_event_id=group_event_id,
            user_id=uid,
            document_type_id=document_type_id,
            file_content=content,
            original_filename=name,
            mime_type=mime,
            actor_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
        )
    except ValueError as e:
        db.rollback()
        code, msg = _err_map(e)
        raise HTTPException(status_code=code, detail=msg) from e

    read = reservation_document_to_read(db, doc)
    db.commit()
    return UploadResponse(document=read)


@router.get("/group-events/{group_event_id}/documents/{document_id}/file")
def download_group_document(
    group_event_id: UUID,
    document_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    tenant_data: tuple[UUID, str | None] = Depends(require_tenant),
):
    from app.modules.reservation_documents.models import ReservationDocument

    tenant_id, _role = tenant_data
    _assert_group_documents_access(request, db, tenant_id, group_event_id)
    doc = db.get(ReservationDocument, document_id)
    if doc is None or doc.tenant_id != tenant_id or doc.group_event_id != group_event_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento no encontrado")
    try:
        data = read_file_bytes(doc.storage_key)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo no encontrado") from None
    return Response(
        content=data,
        media_type=doc.mime_type,
        headers={
            "Content-Disposition": f'inline; filename="{doc.original_filename}"',
        },
    )
