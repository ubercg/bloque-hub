"""Build aggregated operations dashboard data (grouped reservations, KPIs, readiness)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.permissions import STAFF_ROLES
from app.modules.booking.event_summary import build_event_summary_dict, pick_primary_status
from app.modules.booking.models import PaymentVoucher, Reservation, ReservationStatus
from app.modules.fulfillment.services import get_readiness_by_reservation_id
from app.modules.operations.schemas import (
    OperationsKpis,
    ReadinessFlags,
    ReservationGroupSummary,
    ReservationsSummaryResponse,
    SpaceBlocksRead,
    TimeBlockRead,
)
from app.modules.reservation_documents.services import build_completeness

MX_TZ = ZoneInfo("America/Mexico_City")


def today_mexico() -> date:
    return datetime.now(MX_TZ).date()


def _fmt_hm(t: time) -> str:
    return f"{t.hour:02d}:{t.minute:02d}"


def _group_key(r: Reservation) -> UUID:
    """Stable key: group_event_id or reservation id for singleton."""
    return r.group_event_id if r.group_event_id is not None else r.id


def _has_any_voucher(db: Session, reservation_ids: list[UUID]) -> bool:
    if not reservation_ids:
        return False
    n = (
        db.query(func.count(PaymentVoucher.id))
        .filter(PaymentVoucher.reservation_id.in_(reservation_ids))
        .scalar()
    )
    return (n or 0) > 0


def _payment_received(rows: list[Reservation], db: Session) -> bool:
    ids = [r.id for r in rows]
    for r in rows:
        if r.status == ReservationStatus.CONFIRMED:
            return True
        if r.status in (
            ReservationStatus.PAYMENT_UNDER_REVIEW,
            ReservationStatus.AWAITING_PAYMENT,
        ) and _has_any_voucher(db, [r.id]):
            return True
    return _has_any_voucher(db, ids)


def _documents_complete(db: Session, tenant_id: UUID, rows: list[Reservation]) -> bool:
    if not rows:
        return False
    gid = rows[0].group_event_id
    if gid is not None:
        comp = build_completeness(db, tenant_id=tenant_id, group_event_id=gid)
        return comp.is_complete
    return False


def _validation_ready(db: Session, rows: list[Reservation]) -> bool | None:
    """First reservation with a service order wins; None if no OS on any slot."""
    for r in sorted(rows, key=lambda x: (x.fecha, x.hora_inicio, x.id)):
        res = get_readiness_by_reservation_id(r.id, db)
        if res is not None:
            is_ready, _, _, _ = res
            return is_ready
    return None


def _compute_kpis(
    db: Session,
    tenant_id: UUID,
    today: date,
) -> OperationsKpis:
    """KPIs for calendar-day 'today' in Mexico City, tenant-wide."""
    active_statuses = (
        ReservationStatus.PENDING_SLIP,
        ReservationStatus.AWAITING_PAYMENT,
        ReservationStatus.PAYMENT_UNDER_REVIEW,
        ReservationStatus.CONFIRMED,
    )
    q_base = db.query(Reservation).filter(
        Reservation.tenant_id == tenant_id,
        Reservation.fecha == today,
        Reservation.status.in_(active_statuses),
    )
    rows = q_base.all()

    # Distinct operational groups
    group_keys: set[UUID] = set()
    spaces: set[UUID] = set()
    pending_groups: set[UUID] = set()
    confirmed_groups: set[UUID] = set()

    by_group: dict[UUID, list[Reservation]] = defaultdict(list)
    for r in rows:
        by_group[_group_key(r)].append(r)

    for gk, g_rows in by_group.items():
        group_keys.add(gk)
        for r in g_rows:
            spaces.add(r.space_id)
        primary, _ = pick_primary_status(g_rows)
        if primary == ReservationStatus.PENDING_SLIP:
            pending_groups.add(gk)
        if primary == ReservationStatus.CONFIRMED:
            confirmed_groups.add(gk)

    return OperationsKpis(
        events_today=len(group_keys),
        spaces_occupied_today=len(spaces),
        pending_slip_groups_today=len(pending_groups),
        confirmed_groups_today=len(confirmed_groups),
    )


def build_reservations_summary(
    db: Session,
    *,
    tenant_id: UUID,
    role: str | None,
    user_id: UUID | None,
    date_from: date | None,
    date_to: date | None,
    status: ReservationStatus | None,
    space_id: UUID | None,
) -> ReservationsSummaryResponse:
    """
    List reservation groups in the selected filters with merged time blocks and readiness flags.
    Staff roles see all tenant reservations; CUSTOMER sees only own rows.
    """
    q = db.query(Reservation).filter(Reservation.tenant_id == tenant_id)
    if role == "CUSTOMER" and user_id is not None:
        q = q.filter(Reservation.user_id == user_id)
    if date_from is not None:
        q = q.filter(Reservation.fecha >= date_from)
    if date_to is not None:
        q = q.filter(Reservation.fecha <= date_to)
    if status is not None:
        q = q.filter(Reservation.status == status)
    if space_id is not None:
        q = q.filter(Reservation.space_id == space_id)

    rows = q.all()

    # Group filtered rows
    by_key: dict[UUID, list[Reservation]] = defaultdict(list)
    for r in rows:
        by_key[_group_key(r)].append(r)

    out: list[ReservationGroupSummary] = []
    for gk in sorted(by_key.keys(), key=lambda x: str(x)):
        group_rows = by_key[gk]
        group_rows.sort(key=lambda x: (x.fecha, x.hora_inicio, x.id))
        try:
            payload = build_event_summary_dict(db, tenant_id, group_rows)
        except ValueError:
            continue

        primary = payload["event"]["status_primary"]
        mixed = payload["event"]["status_is_mixed"]
        fechas = [r.fecha for r in group_rows]
        spaces_out: list[SpaceBlocksRead] = []
        for sp in payload["spaces"]:
            blocks_flat: list[TimeBlockRead] = []
            for day in sp["days"]:
                d = day["date"]
                for b in day["blocks"]:
                    blocks_flat.append(
                        TimeBlockRead(
                            date=d,
                            start=_fmt_hm(b["start"]),
                            end=_fmt_hm(b["end"]),
                            hours=float(b["hours"]),
                            reservation_ids=list(b["reservation_ids"]),
                        )
                    )
            spaces_out.append(
                SpaceBlocksRead(
                    space_id=sp["space_id"],
                    name=sp["space_name"],
                    blocks=blocks_flat,
                )
            )

        op_id = str(
            group_rows[0].group_event_id
            if group_rows[0].group_event_id is not None
            else group_rows[0].id
        )
        res_ids = [r.id for r in group_rows]

        readiness = ReadinessFlags(
            documents=_documents_complete(db, tenant_id, group_rows),
            payment=_payment_received(group_rows, db),
            validation=_validation_ready(db, group_rows),
        )

        out.append(
            ReservationGroupSummary(
                operational_group_id=op_id,
                group_event_id=group_rows[0].group_event_id,
                reservation_ids=res_ids,
                event_name=payload["event"].get("name"),
                date_from=payload["event"]["date_from"],
                date_to=payload["event"]["date_to"],
                status=primary,
                status_is_mixed=mixed,
                spaces=spaces_out,
                readiness=readiness,
            )
        )

    # Sort: urgency first (PENDING_SLIP), then date_from
    urgency = {
        ReservationStatus.PENDING_SLIP: 0,
        ReservationStatus.AWAITING_PAYMENT: 1,
        ReservationStatus.PAYMENT_UNDER_REVIEW: 2,
        ReservationStatus.CONFIRMED: 3,
        ReservationStatus.EXPIRED: 4,
        ReservationStatus.CANCELLED: 5,
    }

    def sort_key(item: ReservationGroupSummary):
        return (urgency.get(item.status, 99), item.date_from, item.operational_group_id)

    out.sort(key=sort_key)

    kpis = _compute_kpis(db, tenant_id, today_mexico())

    return ReservationsSummaryResponse(kpis=kpis, reservations=out)


def allow_operations_summary_role(role: str | None) -> None:
    """Staff back-office or CUSTOMER (filtered to own reservations in build)."""
    from fastapi import HTTPException, status

    if role in STAFF_ROLES or role == "CUSTOMER":
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient role for operations summary",
    )
