"""Access services: create QR token on reservation confirm."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, time, timezone

from sqlalchemy.orm import Session

from app.modules.access.models import AccessQRToken
from app.modules.booking.models import Reservation


def create_qr_token_for_reservation(reservation: Reservation, db: Session) -> AccessQRToken | None:
    """
    Create or return existing AccessQRToken for a confirmed reservation.
    valid_from = event date 00:00 UTC, valid_until = hora_fin + 2h UTC (FR-14/FR-25).
    One active token per reservation; if one exists, return it without creating duplicate.
    """
    existing = (
        db.query(AccessQRToken)
        .filter(AccessQRToken.reservation_id == reservation.id)
        .first()
    )
    if existing:
        return existing

    # Build valid_from = fecha 00:00 UTC, valid_until = fecha + hora_fin + 2h UTC
    valid_from = datetime.combine(
        reservation.fecha, time(0, 0, 0), tzinfo=timezone.utc
    )
    end_dt = datetime.combine(
        reservation.fecha, reservation.hora_fin, tzinfo=timezone.utc
    )
    valid_until = end_dt + timedelta(hours=2)

    token_qr = str(uuid.uuid4()).replace("-", "")  # 32-char hex, unique

    row = AccessQRToken(
        reservation_id=reservation.id,
        token_qr=token_qr,
        valid_from=valid_from,
        valid_until=valid_until,
    )
    db.add(row)
    db.flush()
    return row
