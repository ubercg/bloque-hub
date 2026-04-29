"""Booking services: state machine and reservation lifecycle."""

from __future__ import annotations

import hashlib
from datetime import date, timedelta, time
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.booking.models import PaymentVoucher, Reservation, ReservationStatus
from app.modules.expediente.services import append_document
from app.modules.inventory.models import Inventory, SlotStatus, Space
from app.modules.inventory.services import (
    SlotNotAvailableError,
    claim_slot_for_reservation,
    release_relationship_blocks_for_reservation_slot,
)

DEFAULT_TTL_MINUTES = 1440


class InvalidStateTransitionError(Exception):
    """Raised when a reservation state transition is not allowed."""


# Valid transitions: from_status -> [to_statuses]
ALLOWED_TRANSITIONS: dict[ReservationStatus, list[ReservationStatus]] = {
    ReservationStatus.PENDING_SLIP: [ReservationStatus.AWAITING_PAYMENT, ReservationStatus.CANCELLED],
    ReservationStatus.AWAITING_PAYMENT: [ReservationStatus.PAYMENT_UNDER_REVIEW, ReservationStatus.CANCELLED],
    ReservationStatus.PAYMENT_UNDER_REVIEW: [ReservationStatus.CONFIRMED, ReservationStatus.EXPIRED],
    ReservationStatus.CONFIRMED: [],
    ReservationStatus.EXPIRED: [],
    ReservationStatus.CANCELLED: [],
}


def _check_transition(current: ReservationStatus, new: ReservationStatus) -> None:
    allowed = ALLOWED_TRANSITIONS.get(current, [])
    if new not in allowed:
        raise InvalidStateTransitionError(
            f"Transition from {current.value} to {new.value} is not allowed"
        )


def can_cancel_reservation(reservation: ReservationStatus) -> bool:
    """True if the reservation is in a state that allows user cancellation."""
    return reservation in (
        ReservationStatus.PENDING_SLIP,
        ReservationStatus.AWAITING_PAYMENT,
    )


class EventDispatcher:
    """Stub for post-confirmation events (e.g. notifications). Replace with Celery in T5."""

    def on_reservation_confirmed(self, reservation: Reservation, db: Session) -> None:
        """Called after reservation is set to CONFIRMED. No-op by default."""
        pass


def create_reservation(
    tenant_id: UUID,
    user_id: UUID,
    space_id: UUID,
    fecha: date,
    hora_inicio: time,
    hora_fin: time,
    db: Session,
    created_from_ip: str | None = None,
    device_fingerprint: str | None = None,
    group_event_id: UUID | None = None,
    event_name: str | None = None,
) -> Reservation:
    """
    Create a reservation in PENDING_SLIP and claim the inventory slot (TTL_BLOCKED).
    Raises SlotNotAvailableError if the slot is not available.
    """
    reservation = Reservation(
        tenant_id=tenant_id,
        user_id=user_id,
        space_id=space_id,
        group_event_id=group_event_id,
        event_name=event_name,
        fecha=fecha,
        hora_inicio=hora_inicio,
        hora_fin=hora_fin,
        status=ReservationStatus.PENDING_SLIP,
        ttl_frozen=False,
        created_from_ip=created_from_ip,
        device_fingerprint=device_fingerprint,
    )
    db.add(reservation)
    db.flush()
    space = db.get(Space, space_id)
    ttl_minutes = space.ttl_minutos if space else DEFAULT_TTL_MINUTES
    reservation.ttl_expires_at = reservation.created_at + timedelta(minutes=ttl_minutes)
    db.flush()
    claim_slot_for_reservation(
        space_id, tenant_id, fecha, hora_inicio, hora_fin, reservation.id, db
    )
    return reservation


def create_reservations_for_event(
    tenant_id: UUID,
    user_id: UUID,
    items: list[tuple[UUID, date, time, time]],
    db: Session,
    created_from_ip: str | None = None,
    device_fingerprint: str | None = None,
    event_name: str | None = None,
) -> tuple[UUID, list[Reservation]]:
    """
    Create multiple reservations grouped under one event identifier.
    The operation is transactional: if any slot is unavailable, caller should rollback.
    """
    group_event_id = uuid4()
    reservations: list[Reservation] = []
    for space_id, fecha, hora_inicio, hora_fin in items:
        reservation = create_reservation(
            tenant_id=tenant_id,
            user_id=user_id,
            space_id=space_id,
            fecha=fecha,
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
            db=db,
            created_from_ip=created_from_ip,
            device_fingerprint=device_fingerprint,
            group_event_id=group_event_id,
            event_name=event_name,
        )
        reservations.append(reservation)
    return group_event_id, reservations


def transition_to_awaiting_payment(reservation: Reservation, db: Session) -> None:
    _check_transition(reservation.status, ReservationStatus.AWAITING_PAYMENT)
    reservation.status = ReservationStatus.AWAITING_PAYMENT
    db.flush()


def transition_to_payment_under_review(reservation: Reservation, db: Session) -> None:
    _check_transition(reservation.status, ReservationStatus.PAYMENT_UNDER_REVIEW)
    reservation.status = ReservationStatus.PAYMENT_UNDER_REVIEW
    reservation.ttl_frozen = True  # Regla 4c: pausa TTL al subir comprobante
    db.flush()


def _get_slot_for_reservation(reservation: Reservation, db: Session) -> Inventory | None:
    stmt = select(Inventory).where(
        Inventory.space_id == reservation.space_id,
        Inventory.fecha == reservation.fecha,
        Inventory.hora_inicio == reservation.hora_inicio,
        Inventory.hora_fin == reservation.hora_fin,
        Inventory.reservation_id == reservation.id,
    )
    return db.execute(stmt).scalars().first()


def confirm_payment(
    reservation: Reservation,
    db: Session,
    event_dispatcher: EventDispatcher | None = None,
) -> None:
    """
    Transition to CONFIRMED, set inventory slot to RESERVED, and call dispatcher.
    If dispatcher raises, the transaction should be rolled back by the caller.
    """
    _check_transition(reservation.status, ReservationStatus.CONFIRMED)
    slot = _get_slot_for_reservation(reservation, db)
    if slot is not None:
        slot.estado = SlotStatus.RESERVED
    reservation.status = ReservationStatus.CONFIRMED
    db.flush()
    from app.modules.reservation_documents.kyc_expediente import (
        sync_kyc_documents_to_expediente_for_reservation,
    )

    sync_kyc_documents_to_expediente_for_reservation(reservation, db)
    dispatcher = event_dispatcher or EventDispatcher()
    dispatcher.on_reservation_confirmed(reservation, db)


def reject_payment(reservation: Reservation, db: Session) -> None:
    """Transition to EXPIRED and release the inventory slot."""
    _check_transition(reservation.status, ReservationStatus.EXPIRED)
    slot = _get_slot_for_reservation(reservation, db)
    if slot is not None:
        slot.estado = SlotStatus.AVAILABLE
        slot.reservation_id = None
        release_relationship_blocks_for_reservation_slot(
            reservation.space_id,
            reservation.tenant_id,
            reservation.fecha,
            reservation.hora_inicio,
            reservation.hora_fin,
            db,
        )
    reservation.status = ReservationStatus.EXPIRED
    db.flush()


def expire_reservation_by_ttl(reservation: Reservation, db: Session) -> None:
    """
    Expire a reservation due to TTL (called by cron). Only allowed for PENDING_SLIP or AWAITING_PAYMENT.
    Sets status to EXPIRED and releases the inventory slot.
    """
    if reservation.status not in (
        ReservationStatus.PENDING_SLIP,
        ReservationStatus.AWAITING_PAYMENT,
    ):
        return
    slot = _get_slot_for_reservation(reservation, db)
    if slot is not None:
        slot.estado = SlotStatus.AVAILABLE
        slot.reservation_id = None
        release_relationship_blocks_for_reservation_slot(
            reservation.space_id,
            reservation.tenant_id,
            reservation.fecha,
            reservation.hora_inicio,
            reservation.hora_fin,
            db,
        )
    reservation.status = ReservationStatus.EXPIRED
    db.flush()
    from app.modules.reservation_documents.services import (
        purge_kyc_drafts_for_group_if_all_terminal,
    )

    purge_kyc_drafts_for_group_if_all_terminal(
        db, tenant_id=reservation.tenant_id, group_event_id=reservation.group_event_id
    )


def cancel_reservation(reservation: Reservation, db: Session) -> None:
    """
    Cancel a reservation (user-initiated). Allowed only for PENDING_SLIP or AWAITING_PAYMENT.
    Sets status to CANCELLED and releases the inventory slot.
    """
    _check_transition(reservation.status, ReservationStatus.CANCELLED)
    slot = _get_slot_for_reservation(reservation, db)
    if slot is not None:
        slot.estado = SlotStatus.AVAILABLE
        slot.reservation_id = None
        release_relationship_blocks_for_reservation_slot(
            reservation.space_id,
            reservation.tenant_id,
            reservation.fecha,
            reservation.hora_inicio,
            reservation.hora_fin,
            db,
        )
    reservation.status = ReservationStatus.CANCELLED
    db.flush()
    from app.modules.reservation_documents.services import (
        purge_kyc_drafts_for_group_if_all_terminal,
    )

    purge_kyc_drafts_for_group_if_all_terminal(
        db, tenant_id=reservation.tenant_id, group_event_id=reservation.group_event_id
    )


def release_inventory_for_reservation(reservation: Reservation, db: Session) -> None:
    """
    Defensive cleanup: release any inventory slot linked to this reservation id.
    Useful when reservation was already CANCELLED/EXPIRED but slot stayed blocked.
    """
    slot = (
        db.query(Inventory)
        .filter(Inventory.reservation_id == reservation.id)
        .first()
    )
    if slot is None:
        return
    if slot.estado != SlotStatus.RESERVED:
        slot.estado = SlotStatus.AVAILABLE
        slot.reservation_id = None
        release_relationship_blocks_for_reservation_slot(
            reservation.space_id,
            reservation.tenant_id,
            reservation.fecha,
            reservation.hora_inicio,
            reservation.hora_fin,
            db,
        )
    db.flush()


def upload_payment_voucher(
    reservation: Reservation,
    file_content: bytes,
    file_type: str,
    tenant_id: UUID,
    uploaded_by_ip: str | None,
    db: Session,
) -> PaymentVoucher:
    """
    Upload and save a payment voucher (comprobante de pago) for a reservation.

    This function:
    1. Computes SHA-256 hash of file content
    2. Creates storage directory if needed
    3. Saves file to filesystem with UUID-based name
    4. Creates PaymentVoucher database record
    5. Registers document in ExpedienteDocument (Chain of Trust)

    All operations are atomic (transaction-safe).

    Args:
        reservation: The reservation this voucher is for
        file_content: Raw bytes of the uploaded file
        file_type: MIME type (e.g., "application/pdf")
        tenant_id: Tenant ID for RLS
        uploaded_by_ip: Client IP address (nullable)
        db: Database session

    Returns:
        PaymentVoucher: The created voucher record

    Raises:
        IntegrityError: If SHA-256 hash already exists (duplicate file)
    """
    # Calculate SHA-256 hash
    sha256_hash = hashlib.sha256(file_content).hexdigest()

    # Determine file extension from MIME type
    ext_map = {
        "application/pdf": ".pdf",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/heic": ".heic",
    }
    ext = ext_map.get(file_type, ".bin")

    # Create storage directory
    storage_path = Path(settings.PAYMENT_VOUCHERS_STORAGE_PATH)
    storage_path.mkdir(parents=True, exist_ok=True)

    # Create voucher record (this will raise IntegrityError if hash exists due to UNIQUE constraint)
    voucher = PaymentVoucher(
        tenant_id=tenant_id,
        reservation_id=reservation.id,
        file_url="",  # Will be set after we have the ID
        file_type=file_type,
        file_size_kb=len(file_content) // 1024,
        sha256_hash=sha256_hash,
        uploaded_by_ip=uploaded_by_ip,
    )
    db.add(voucher)
    db.flush()  # Get the ID

    # Generate safe filename and save to disk
    safe_filename = f"{voucher.id}{ext}"
    full_path = storage_path / safe_filename
    full_path.write_bytes(file_content)

    # Update file_url with relative path
    voucher.file_url = safe_filename

    # Register in ExpedienteDocument (Chain of Trust)
    append_document(
        db,
        tenant_id=tenant_id,
        document_type="PAYMENT_VOUCHER",
        doc_sha256=sha256_hash,
        document_url=safe_filename,
        reservation_id=reservation.id,
    )

    db.flush()
    return voucher
