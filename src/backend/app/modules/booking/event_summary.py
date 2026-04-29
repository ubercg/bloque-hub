"""Agrupación de slots por espacio/día y fusión de bloques contiguos para resumen de evento."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.booking.models import Reservation, ReservationStatus
from app.modules.inventory.models import Space
from app.modules.pricing.services import get_quote_for_space


def _slot_duration_hours(hora_inicio: time, hora_fin: time) -> Decimal:
    start_minutes = hora_inicio.hour * 60 + hora_inicio.minute
    end_minutes = hora_fin.hour * 60 + hora_fin.minute
    diff = max(0, end_minutes - start_minutes)
    return (Decimal(diff) / Decimal(60)).quantize(Decimal("0.01"))


def _time_equal(a: time, b: time) -> bool:
    return a.hour == b.hour and a.minute == b.minute and a.second == b.second


def _time_to_seconds(t: time) -> int:
    return t.hour * 3600 + t.minute * 60 + t.second


def hours_between_times(start: time, end: time) -> Decimal:
    diff = _time_to_seconds(end) - _time_to_seconds(start)
    if diff <= 0:
        return Decimal("0")
    return (Decimal(diff) / Decimal(3600)).quantize(Decimal("0.01"))


@dataclass(frozen=True)
class MergedBlock:
    start: time
    end: time
    reservation_ids: tuple[UUID, ...]

    @property
    def hours(self) -> Decimal:
        return hours_between_times(self.start, self.end)


def merge_consecutive_slots(rows: list[Reservation]) -> list[MergedBlock]:
    """
    Por un mismo (space_id, fecha), ordena por hora_inicio y fusiona slots donde
    hora_fin del anterior == hora_inicio del siguiente.
    """
    if not rows:
        return []
    sorted_rows = sorted(rows, key=lambda r: (r.hora_inicio, r.hora_fin, r.id))
    blocks: list[MergedBlock] = []
    cur_start = sorted_rows[0].hora_inicio
    cur_end = sorted_rows[0].hora_fin
    cur_ids: list[UUID] = [sorted_rows[0].id]

    for r in sorted_rows[1:]:
        if _time_equal(cur_end, r.hora_inicio):
            cur_end = r.hora_fin
            cur_ids.append(r.id)
        else:
            blocks.append(MergedBlock(start=cur_start, end=cur_end, reservation_ids=tuple(cur_ids)))
            cur_start = r.hora_inicio
            cur_end = r.hora_fin
            cur_ids = [r.id]

    blocks.append(MergedBlock(start=cur_start, end=cur_end, reservation_ids=tuple(cur_ids)))
    return blocks


# Orden de "urgencia" para el cliente: el estado que más requiere acción primero.
_STATUS_URGENCY: tuple[ReservationStatus, ...] = (
    ReservationStatus.CANCELLED,
    ReservationStatus.EXPIRED,
    ReservationStatus.PENDING_SLIP,
    ReservationStatus.AWAITING_PAYMENT,
    ReservationStatus.PAYMENT_UNDER_REVIEW,
    ReservationStatus.CONFIRMED,
)


def pick_primary_status(reservations: list[Reservation]) -> tuple[ReservationStatus, bool]:
    """Devuelve (status_representativo, is_mixed)."""
    if not reservations:
        return ReservationStatus.PENDING_SLIP, False
    statuses = {r.status for r in reservations}
    if len(statuses) == 1:
        return next(iter(statuses)), False
    for s in _STATUS_URGENCY:
        if s in statuses:
            return s, True
    return reservations[0].status, True


def list_reservations_for_event(db: Session, tenant_id: UUID, anchor: Reservation) -> list[Reservation]:
    """Todas las reservas del mismo grupo, o solo la ancla si no hay group_event_id."""
    if anchor.group_event_id is not None:
        rows = (
            db.query(Reservation)
            .filter(
                Reservation.tenant_id == tenant_id,
                Reservation.group_event_id == anchor.group_event_id,
            )
            .order_by(Reservation.fecha, Reservation.hora_inicio, Reservation.id)
            .all()
        )
        return rows
    return [anchor]


def space_name_map(db: Session, tenant_id: UUID, space_ids: set[UUID]) -> dict[UUID, str]:
    if not space_ids:
        return {}
    rows = (
        db.query(Space)
        .filter(Space.tenant_id == tenant_id, Space.id.in_(space_ids))
        .all()
    )
    return {s.id: s.name for s in rows}


def compute_precotizacion_line_items(
    db: Session,
    tenant_id: UUID,
    reservations: list[Reservation],
) -> tuple[list[dict], Decimal]:
    """
    Líneas para PDF: una fila por bloque fusionado (espacio, fecha, rango, precio = suma de slots del bloque).
    """
    by_space_date: dict[tuple[UUID, date], list[Reservation]] = defaultdict(list)
    for r in reservations:
        by_space_date[(r.space_id, r.fecha)].append(r)

    lines: list[dict] = []
    subtotal = Decimal("0.00")

    for (space_id, fecha), group in sorted(
        by_space_date.items(),
        key=lambda x: (x[0][1], str(x[0][0])),
    ):
        blocks = merge_consecutive_slots(group)
        for b in blocks:
            block_price = Decimal("0.00")
            for rid in b.reservation_ids:
                res = next(x for x in group if x.id == rid)
                dur = _slot_duration_hours(res.hora_inicio, res.hora_fin)
                q = get_quote_for_space(
                    db=db,
                    tenant_id=tenant_id,
                    space_id=res.space_id,
                    target_date=res.fecha,
                    duration_hours=dur,
                )
                block_price += Decimal(str(q["total_price"]))
            block_price = block_price.quantize(Decimal("0.01"))
            subtotal += block_price
            lines.append(
                {
                    "space_id": space_id,
                    "fecha": fecha,
                    "hora_inicio": b.start,
                    "hora_fin": b.end,
                    "hours": float(b.hours),
                    "precio": float(block_price),
                    "reservation_ids": list(b.reservation_ids),
                }
            )

    return lines, subtotal.quantize(Decimal("0.01"))


def build_event_summary_dict(
    db: Session,
    tenant_id: UUID,
    reservations: list[Reservation],
) -> dict:
    """Construye el dict compatible con EventSummaryResponse (sin validar Pydantic aquí)."""
    if not reservations:
        raise ValueError("empty reservations")

    space_ids = {r.space_id for r in reservations}
    names = space_name_map(db, tenant_id, space_ids)

    by_space: dict[UUID, list[Reservation]] = defaultdict(list)
    for r in reservations:
        by_space[r.space_id].append(r)

    total_hours = Decimal("0")
    spaces_out: list[dict] = []

    for space_id in sorted(by_space.keys(), key=lambda sid: (names.get(sid, ""), str(sid))):
        rows = by_space[space_id]
        by_date: dict[date, list[Reservation]] = defaultdict(list)
        for r in rows:
            by_date[r.fecha].append(r)

        days_out: list[dict] = []
        for d in sorted(by_date.keys()):
            day_rows = by_date[d]
            merged = merge_consecutive_slots(day_rows)
            blocks_out: list[dict] = []
            for b in merged:
                h = b.hours
                total_hours += h
                blocks_out.append(
                    {
                        "start": b.start,
                        "end": b.end,
                        "hours": float(h),
                        "reservation_ids": list(b.reservation_ids),
                    }
                )
            days_out.append({"date": d, "blocks": blocks_out})

        spaces_out.append(
            {
                "space_id": space_id,
                "space_name": names.get(space_id, f"Espacio {str(space_id)[:8].upper()}"),
                "days": days_out,
            }
        )

    fechas = [r.fecha for r in reservations]
    date_from = min(fechas)
    date_to = max(fechas)
    first = reservations[0]
    primary, mixed = pick_primary_status(reservations)

    return {
        "event": {
            "group_event_id": first.group_event_id,
            "name": first.event_name,
            "date_from": date_from,
            "date_to": date_to,
            "status_primary": primary,
            "status_is_mixed": mixed,
        },
        "totals": {
            "unique_spaces": len(by_space),
            "total_hours": float(total_hours.quantize(Decimal("0.01"))),
        },
        "spaces": spaces_out,
    }
