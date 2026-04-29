"""Lógica de borradores KYC: subida versionada, completitud, límites."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.audit.service import append_audit_log
from app.modules.booking.models import Reservation, ReservationStatus
from app.modules.reservation_documents.models import DocumentTypeDefinition, ReservationDocument
from app.modules.reservation_documents.schemas import (
    CompletenessResponse,
    DocumentItemStatus,
    ReservationDocumentRead,
)


OTRO_CODE = "OTRO"
_ALLOWED_MIME_NORMALIZED = frozenset(
    {"application/pdf", "image/jpeg", "image/png", "image/jpg"}
)


def normalize_mime(mime: str) -> str:
    m = (mime or "").lower().strip()
    if m == "image/jpg":
        return "image/jpeg"
    return m


def list_global_definitions(db: Session) -> list[DocumentTypeDefinition]:
    stmt = (
        select(DocumentTypeDefinition)
        .where(
            DocumentTypeDefinition.tenant_id.is_(None),
            DocumentTypeDefinition.active.is_(True),
        )
        .order_by(DocumentTypeDefinition.sort_order, DocumentTypeDefinition.code)
    )
    return list(db.execute(stmt).scalars().all())


def _get_reservations_for_group(
    db: Session, tenant_id: uuid.UUID, group_event_id: uuid.UUID
) -> list[Reservation]:
    stmt = select(Reservation).where(
        Reservation.tenant_id == tenant_id,
        Reservation.group_event_id == group_event_id,
    )
    return list(db.execute(stmt).scalars().all())


def verify_customer_owns_group(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    group_event_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    rows = _get_reservations_for_group(db, tenant_id, group_event_id)
    if not rows:
        return False
    return all(r.user_id == user_id for r in rows)


def group_belongs_to_tenant(
    db: Session, *, tenant_id: uuid.UUID, group_event_id: uuid.UUID
) -> bool:
    """
    True si existe al menos una reserva del tenant con ese group_event_id,
    o cuyo id coincide con group_event_id (evento de un solo slot con documentos bajo id de reserva).
    """
    from sqlalchemy import or_

    stmt = (
        select(Reservation.id)
        .where(
            Reservation.tenant_id == tenant_id,
            or_(
                Reservation.group_event_id == group_event_id,
                Reservation.id == group_event_id,
            ),
        )
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none() is not None


def group_has_discount_code(db: Session, tenant_id: uuid.UUID, group_event_id: uuid.UUID) -> bool:
    stmt = (
        select(Reservation.discount_code_id)
        .where(
            Reservation.tenant_id == tenant_id,
            Reservation.group_event_id == group_event_id,
            Reservation.discount_code_id.isnot(None),
        )
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none() is not None


def _active_docs_by_type(
    db: Session, tenant_id: uuid.UUID, group_event_id: uuid.UUID
) -> dict[uuid.UUID, list[ReservationDocument]]:
    stmt = (
        select(ReservationDocument)
        .where(
            ReservationDocument.tenant_id == tenant_id,
            ReservationDocument.group_event_id == group_event_id,
            ReservationDocument.status == "ACTIVE",
        )
        .order_by(ReservationDocument.created_at.desc())
    )
    docs = list(db.execute(stmt).scalars().all())
    by_type: dict[uuid.UUID, list[ReservationDocument]] = {}
    for d in docs:
        by_type.setdefault(d.document_type_id, []).append(d)
    return by_type


def _definition_applies(
    d: DocumentTypeDefinition, *, has_discount: bool
) -> tuple[bool, bool]:
    """Returns (is_required_for_completeness, include_in_required_list)."""
    if d.requires_condition == "DISCOUNT_CODE":
        return (has_discount and d.required, has_discount)
    return (d.required, True)


def build_completeness(
    db: Session, *, tenant_id: uuid.UUID, group_event_id: uuid.UUID
) -> CompletenessResponse:
    defs = list_global_definitions(db)
    has_discount = group_has_discount_code(db, tenant_id, group_event_id)
    by_type = _active_docs_by_type(db, tenant_id, group_event_id)

    required_out: list[DocumentItemStatus] = []
    optional_out: list[DocumentItemStatus] = []
    req_ok = 0
    req_needed = 0

    for d in defs:
        need, show = _definition_applies(d, has_discount=has_discount)
        if not show:
            continue
        active_list = by_type.get(d.id, [])
        if d.code == OTRO_CODE:
            status: DocumentItemStatus = DocumentItemStatus(
                type=d.code,
                label=d.label,
                status="OK" if active_list else "MISSING",
                document_id=active_list[0].id if active_list else None,
            )
            optional_out.append(status)
            continue

        if active_list:
            st = "OK"
            doc_id = active_list[0].id
        else:
            st = "MISSING"
            doc_id = None
        item = DocumentItemStatus(
            type=d.code, label=d.label, status=st, document_id=doc_id
        )
        if need:
            required_out.append(item)
            req_needed += 1
            if st == "OK":
                req_ok += 1
        else:
            optional_out.append(item)

    is_complete = req_needed == 0 or req_ok == req_needed
    return CompletenessResponse(
        required=required_out, optional=optional_out, is_complete=is_complete
    )


def _total_active_bytes(
    db: Session, tenant_id: uuid.UUID, group_event_id: uuid.UUID
) -> int:
    stmt = select(func.coalesce(func.sum(ReservationDocument.size_bytes), 0)).where(
        ReservationDocument.tenant_id == tenant_id,
        ReservationDocument.group_event_id == group_event_id,
        ReservationDocument.status == "ACTIVE",
    )
    return int(db.execute(stmt).scalar_one() or 0)


def _ext_for_mime(mime: str) -> str:
    m = normalize_mime(mime)
    if m == "application/pdf":
        return ".pdf"
    if m in ("image/jpeg", "image/jpg"):
        return ".jpg"
    if m == "image/png":
        return ".png"
    return ".bin"


def _storage_dir() -> Path:
    p = Path(settings.RESERVATION_DOCUMENTS_STORAGE_PATH)
    p.mkdir(parents=True, exist_ok=True)
    return p


def upload_document_version(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    group_event_id: uuid.UUID,
    user_id: uuid.UUID,
    document_type_id: uuid.UUID,
    file_content: bytes,
    original_filename: str,
    mime_type: str,
    actor_ip: str | None,
    user_agent: str | None,
) -> ReservationDocument:
    rows = _get_reservations_for_group(db, tenant_id, group_event_id)
    if not rows:
        raise ValueError("GROUP_NOT_FOUND")
    if not all(r.user_id == user_id for r in rows):
        raise ValueError("FORBIDDEN")
    if any(
        r.status
        not in (
            ReservationStatus.PENDING_SLIP,
            ReservationStatus.AWAITING_PAYMENT,
        )
        for r in rows
    ):
        raise ValueError("INVALID_STATE")

    dfn = db.get(DocumentTypeDefinition, document_type_id)
    if dfn is None or not dfn.active:
        raise ValueError("UNKNOWN_DOCUMENT_TYPE")

    if dfn.tenant_id is not None and dfn.tenant_id != tenant_id:
        raise ValueError("UNKNOWN_DOCUMENT_TYPE")

    mime = normalize_mime(mime_type)
    allowed_raw = dfn.mime_rules if isinstance(dfn.mime_rules, list) else []
    allowed_normalized = {normalize_mime(str(x)) for x in allowed_raw}
    if allowed_normalized and mime not in allowed_normalized:
        raise ValueError("INVALID_MIME")
    if not allowed_normalized and mime not in _ALLOWED_MIME_NORMALIZED:
        raise ValueError("INVALID_MIME")

    if dfn.requires_condition == "DISCOUNT_CODE" and not group_has_discount_code(
        db, tenant_id, group_event_id
    ):
        raise ValueError("DISCOUNT_DOC_NOT_APPLICABLE")

    size_b = len(file_content)
    if size_b > settings.MAX_KYC_FILE_BYTES:
        raise ValueError("FILE_TOO_LARGE")
    if size_b <= 0:
        raise ValueError("FILE_EMPTY")

    if dfn.code != OTRO_CODE:
        stmt = select(ReservationDocument).where(
            ReservationDocument.tenant_id == tenant_id,
            ReservationDocument.group_event_id == group_event_id,
            ReservationDocument.document_type_id == document_type_id,
            ReservationDocument.status == "ACTIVE",
        )
        old = db.execute(stmt).scalars().first()
    else:
        old = None

    current_total = _total_active_bytes(db, tenant_id, group_event_id)
    delta = size_b
    if dfn.code != OTRO_CODE and old is not None:
        delta = size_b - old.size_bytes
    if current_total + delta > settings.MAX_KYC_GROUP_BYTES:
        raise ValueError("GROUP_QUOTA_EXCEEDED")

    sha = hashlib.sha256(file_content).hexdigest()

    doc_id = uuid.uuid4()
    ext = _ext_for_mime(mime)
    storage_key = f"{tenant_id}/{group_event_id}/{doc_id}{ext}"
    full_path = _storage_dir() / storage_key
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(file_content)

    new_doc = ReservationDocument(
        id=doc_id,
        tenant_id=tenant_id,
        group_event_id=group_event_id,
        document_type_id=document_type_id,
        storage_key=storage_key,
        original_filename=original_filename[:500],
        mime_type=mime,
        size_bytes=size_b,
        sha256=sha,
        status="ACTIVE",
    )
    db.add(new_doc)
    db.flush()

    if old is not None:
        old.status = "SUPERSEDED"
        old.superseded_by_id = new_doc.id
        db.flush()
        append_audit_log(
            db,
            tenant_id=tenant_id,
            tabla="reservation_documents",
            registro_id=old.id,
            accion="UPDATE",
            valor_anterior={"status": "ACTIVE"},
            valor_nuevo={
                "status": "SUPERSEDED",
                "superseded_by_id": str(new_doc.id),
            },
            actor_id=user_id,
            actor_ip=actor_ip,
            actor_user_agent=user_agent,
        )

    append_audit_log(
        db,
        tenant_id=tenant_id,
        tabla="reservation_documents",
        registro_id=new_doc.id,
        accion="CREATE",
        valor_nuevo={
            "group_event_id": str(group_event_id),
            "document_type_id": str(document_type_id),
            "storage_key": storage_key,
            "supersedes": str(old.id) if old else None,
        },
        actor_id=user_id,
        actor_ip=actor_ip,
        actor_user_agent=user_agent,
    )
    return new_doc


def list_active_documents(
    db: Session, *, tenant_id: uuid.UUID, group_event_id: uuid.UUID
) -> list[ReservationDocumentRead]:
    stmt = (
        select(ReservationDocument, DocumentTypeDefinition.code)
        .join(
            DocumentTypeDefinition,
            ReservationDocument.document_type_id == DocumentTypeDefinition.id,
        )
        .where(
            ReservationDocument.tenant_id == tenant_id,
            ReservationDocument.group_event_id == group_event_id,
            ReservationDocument.status == "ACTIVE",
        )
        .order_by(ReservationDocument.created_at.desc())
    )
    out: list[ReservationDocumentRead] = []
    for doc, code in db.execute(stmt).all():
        out.append(
            ReservationDocumentRead(
                id=doc.id,
                group_event_id=doc.group_event_id,
                document_type_id=doc.document_type_id,
                document_type_code=code,
                storage_key=doc.storage_key,
                original_filename=doc.original_filename,
                mime_type=doc.mime_type,
                size_bytes=doc.size_bytes,
                sha256=doc.sha256,
                status=doc.status,
                created_at=doc.created_at,
                superseded_by_id=doc.superseded_by_id,
            )
        )
    return out


def list_documents_with_history(
    db: Session, *, tenant_id: uuid.UUID, group_event_id: uuid.UUID
) -> list[ReservationDocumentRead]:
    stmt = (
        select(ReservationDocument, DocumentTypeDefinition.code)
        .join(
            DocumentTypeDefinition,
            ReservationDocument.document_type_id == DocumentTypeDefinition.id,
        )
        .where(
            ReservationDocument.tenant_id == tenant_id,
            ReservationDocument.group_event_id == group_event_id,
        )
        .order_by(ReservationDocument.created_at.desc())
    )
    out: list[ReservationDocumentRead] = []
    for doc, code in db.execute(stmt).all():
        out.append(
            ReservationDocumentRead(
                id=doc.id,
                group_event_id=doc.group_event_id,
                document_type_id=doc.document_type_id,
                document_type_code=code,
                storage_key=doc.storage_key,
                original_filename=doc.original_filename,
                mime_type=doc.mime_type,
                size_bytes=doc.size_bytes,
                sha256=doc.sha256,
                status=doc.status,
                created_at=doc.created_at,
                superseded_by_id=doc.superseded_by_id,
            )
        )
    return out


def purge_kyc_drafts_for_group_if_all_terminal(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    group_event_id: uuid.UUID | None,
) -> int:
    """
    Elimina filas de borradores KYC y archivos en disco cuando todas las reservas
    del grupo están en EXPIRED o CANCELLED (sin CONFIRMED ni flujos activos).
    No toca expediente_documents. Requiere política RLS DELETE o rol SUPERADMIN.
    """
    if group_event_id is None:
        return 0
    stmt = select(Reservation.status).where(
        Reservation.tenant_id == tenant_id,
        Reservation.group_event_id == group_event_id,
    )
    statuses = list(db.execute(stmt).scalars().all())
    if not statuses:
        return 0
    terminal = {ReservationStatus.EXPIRED, ReservationStatus.CANCELLED}
    if any(s not in terminal for s in statuses):
        return 0

    stmt_docs = select(ReservationDocument).where(
        ReservationDocument.tenant_id == tenant_id,
        ReservationDocument.group_event_id == group_event_id,
    )
    docs = list(db.execute(stmt_docs).scalars().all())
    if not docs:
        return 0
    root = _storage_dir()
    for d in docs:
        try:
            (root / d.storage_key).unlink(missing_ok=True)
        except OSError:
            pass
    db.execute(
        delete(ReservationDocument).where(
            ReservationDocument.tenant_id == tenant_id,
            ReservationDocument.group_event_id == group_event_id,
        )
    )
    db.flush()
    return len(docs)


def read_file_bytes(storage_key: str) -> bytes:
    path = _storage_dir() / storage_key
    if not path.is_file():
        raise FileNotFoundError(storage_key)
    return path.read_bytes()


def reservation_document_to_read(
    db: Session, doc: ReservationDocument, *, document_type_code: str | None = None
) -> ReservationDocumentRead:
    code = document_type_code
    if code is None:
        dfn = db.get(DocumentTypeDefinition, doc.document_type_id)
        code = dfn.code if dfn else ""
    return ReservationDocumentRead(
        id=doc.id,
        group_event_id=doc.group_event_id,
        document_type_id=doc.document_type_id,
        document_type_code=code,
        storage_key=doc.storage_key,
        original_filename=doc.original_filename,
        mime_type=doc.mime_type,
        size_bytes=doc.size_bytes,
        sha256=doc.sha256,
        status=doc.status,
        created_at=doc.created_at,
        superseded_by_id=doc.superseded_by_id,
    )
