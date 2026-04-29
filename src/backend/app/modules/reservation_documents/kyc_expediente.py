"""Un solo punto de append a expediente_documents al pasar a CONFIRMED (anchor reservation)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.booking.models import Reservation, ReservationStatus
from app.modules.expediente.services import append_document
from app.modules.reservation_documents.models import DocumentTypeDefinition, ReservationDocument


def _anchor_reservation_id(
    db: Session, group_event_id: uuid.UUID, tenant_id: uuid.UUID
) -> uuid.UUID | None:
    stmt = (
        select(Reservation.id)
        .where(
            Reservation.group_event_id == group_event_id,
            Reservation.tenant_id == tenant_id,
        )
        .order_by(Reservation.id.asc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def _expediente_has_type(
    db: Session,
    *,
    anchor_reservation_id: uuid.UUID,
    document_type_code: str,
) -> bool:
    from app.modules.expediente.models import ExpedienteDocument

    stmt = (
        select(ExpedienteDocument.id)
        .where(
            ExpedienteDocument.reservation_id == anchor_reservation_id,
            ExpedienteDocument.document_type == document_type_code,
        )
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none() is not None


def sync_kyc_documents_to_expediente_for_reservation(
    reservation: Reservation,
    db: Session,
) -> None:
    """
    Al confirmar pago (CONFIRMED), vincula los borradores KYC ACTIVE al expediente
    (append-only), una vez por tipo, solo desde la reserva ancla del grupo.
    Idempotente: no duplica si ya existe el mismo document_type en expediente.
    """
    if reservation.status != ReservationStatus.CONFIRMED:
        return
    gid = reservation.group_event_id
    if gid is None:
        return
    anchor = _anchor_reservation_id(db, gid, reservation.tenant_id)
    if anchor is None:
        return
    if reservation.id != anchor:
        return

    stmt = (
        select(ReservationDocument, DocumentTypeDefinition.code)
        .join(
            DocumentTypeDefinition,
            ReservationDocument.document_type_id == DocumentTypeDefinition.id,
        )
        .where(
            ReservationDocument.tenant_id == reservation.tenant_id,
            ReservationDocument.group_event_id == gid,
            ReservationDocument.status == "ACTIVE",
        )
    )
    rows = db.execute(stmt).all()
    for doc, code in rows:
        if _expediente_has_type(db, anchor_reservation_id=anchor, document_type_code=code):
            continue
        append_document(
            db,
            tenant_id=reservation.tenant_id,
            document_type=code,
            doc_sha256=doc.sha256,
            document_url=doc.storage_key,
            reservation_id=anchor,
            contract_id=None,
        )
