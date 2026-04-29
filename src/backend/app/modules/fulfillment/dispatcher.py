"""Event dispatcher that creates MasterServiceOrder on reservation confirmed."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.booking.models import Reservation
from app.modules.fulfillment.services import create_os_for_reservation


class FulfillmentEventDispatcher:
    """Implements reservation.confirmed by creating a MasterServiceOrder."""

    def on_reservation_confirmed(self, reservation: Reservation, db: Session) -> None:
        create_os_for_reservation(reservation, db)
