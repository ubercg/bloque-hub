"""Inventory services: cycle validation, hierarchical blocking, and availability."""

from __future__ import annotations

import calendar
from collections import deque
from datetime import date, time, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.inventory.models import Inventory, SlotStatus, SpaceBookingRule, SpaceRelationship


class SlotNotAvailableError(Exception):
    """Raised when the slot cannot be claimed (already booked or blocked)."""


_HARD_BLOCK_STATUSES = {
    SlotStatus.TTL_BLOCKED,
    SlotStatus.RESERVED,
    SlotStatus.SOFT_HOLD,
    SlotStatus.MAINTENANCE,
}


def _derived_relationship_block(
    space_id: UUID,
    fecha: date,
    hora_inicio: time,
    hora_fin: time,
    db: Session,
) -> SlotStatus | None:
    """
    Infer slot blocking from parent/child relationships even if shadow inventory rows
    were not materialized yet.
    """
    # If this space is a child, parent reserved/blocked makes child unavailable.
    parent_rel = (
        db.query(SpaceRelationship.parent_space_id)
        .filter(SpaceRelationship.child_space_id == space_id)
        .first()
    )
    if parent_rel is not None:
        parent_id = parent_rel[0]
        parent_row = (
            db.query(Inventory)
            .filter(
                Inventory.space_id == parent_id,
                Inventory.fecha == fecha,
                Inventory.hora_inicio == hora_inicio,
                Inventory.hora_fin == hora_fin,
                Inventory.estado.in_([SlotStatus.TTL_BLOCKED, SlotStatus.RESERVED, SlotStatus.SOFT_HOLD, SlotStatus.MAINTENANCE]),
            )
            .first()
        )
        if parent_row is not None:
            return SlotStatus.BLOCKED_BY_PARENT

    # If this space is a parent, any child reserved/blocked makes parent unavailable.
    child_ids = [
        r[0]
        for r in (
            db.query(SpaceRelationship.child_space_id)
            .filter(SpaceRelationship.parent_space_id == space_id)
            .all()
        )
    ]
    if child_ids:
        child_row = (
            db.query(Inventory)
            .filter(
                Inventory.space_id.in_(child_ids),
                Inventory.fecha == fecha,
                Inventory.hora_inicio == hora_inicio,
                Inventory.hora_fin == hora_fin,
                Inventory.estado.in_([SlotStatus.TTL_BLOCKED, SlotStatus.RESERVED, SlotStatus.SOFT_HOLD, SlotStatus.MAINTENANCE]),
            )
            .first()
        )
        if child_row is not None:
            return SlotStatus.BLOCKED_BY_CHILD

    return None


def _get_or_create_slot(
    space_id: UUID,
    tenant_id: UUID,
    fecha: date,
    hora_inicio: time,
    hora_fin: time,
    db: Session,
) -> Inventory:
    """Return existing inventory row for the slot or create one with AVAILABLE."""
    row = (
        db.query(Inventory)
        .filter(
            Inventory.space_id == space_id,
            Inventory.fecha == fecha,
            Inventory.hora_inicio == hora_inicio,
            Inventory.hora_fin == hora_fin,
        )
        .first()
    )
    if row is not None:
        return row
    row = Inventory(
        space_id=space_id,
        tenant_id=tenant_id,
        fecha=fecha,
        hora_inicio=hora_inicio,
        hora_fin=hora_fin,
        estado=SlotStatus.AVAILABLE,
    )
    db.add(row)
    db.flush()
    return row


def claim_slot_for_reservation(
    space_id: UUID,
    tenant_id: UUID,
    fecha: date,
    hora_inicio: time,
    hora_fin: time,
    reservation_id: UUID,
    db: Session,
) -> None:
    """
    Get or create the inventory slot, lock it, and set TTL_BLOCKED + reservation_id.
    Raises SlotNotAvailableError if slot is not AVAILABLE or already has a reservation_id.
    Call within a transaction after creating the Reservation.

    CA-08: Re-verification occurs atomically inside the SELECT FOR UPDATE lock.
    Also checks for overlapping blocked slots in the same time range.
    """
    # Validate granularity before attempting claim
    min_duration, allowed_starts = _get_booking_rule(space_id, db)
    start_str = hora_inicio.strftime("%H:%M")
    if start_str not in allowed_starts:
        raise SlotNotAvailableError(
            f"Start time {start_str} is not valid for this space"
        )
    requested_minutes = (hora_fin.hour * 60 + hora_fin.minute) - (hora_inicio.hour * 60 + hora_inicio.minute)
    if requested_minutes < min_duration:
        raise SlotNotAvailableError(
            f"Minimum duration is {min_duration} minutes"
        )

    slot = _get_or_create_slot(space_id, tenant_id, fecha, hora_inicio, hora_fin, db)
    stmt = (
        select(Inventory)
        .where(Inventory.id == slot.id)
        .with_for_update()
    )
    row = db.execute(stmt).scalar_one()
    if row.estado != SlotStatus.AVAILABLE or row.reservation_id is not None:
        raise SlotNotAvailableError("Slot is not available for reservation")

    # CA-08: Check for overlapping slots that are not AVAILABLE
    overlapping = (
        db.query(Inventory)
        .filter(
            Inventory.space_id == space_id,
            Inventory.fecha == fecha,
            Inventory.id != slot.id,
            Inventory.hora_inicio < hora_fin,
            Inventory.hora_fin > hora_inicio,
            Inventory.estado != SlotStatus.AVAILABLE,
        )
        .first()
    )
    if overlapping is not None:
        raise SlotNotAvailableError("Overlapping slot is blocked or reserved")

    # Relationship-aware locking (parent/child same slot).
    rel_parent = (
        db.query(SpaceRelationship.parent_space_id)
        .filter(
            SpaceRelationship.tenant_id == tenant_id,
            SpaceRelationship.child_space_id == space_id,
        )
        .first()
    )
    rel_children = (
        db.query(SpaceRelationship.child_space_id)
        .filter(
            SpaceRelationship.tenant_id == tenant_id,
            SpaceRelationship.parent_space_id == space_id,
        )
        .all()
    )

    parent_id = rel_parent[0] if rel_parent else None
    child_ids = [r[0] for r in rel_children]

    # Child selected: parent must be free (or already blocked by a child).
    if parent_id is not None:
        parent_slot = _get_or_create_slot(
            parent_id, tenant_id, fecha, hora_inicio, hora_fin, db
        )
        parent_locked = db.execute(
            select(Inventory).where(Inventory.id == parent_slot.id).with_for_update()
        ).scalar_one()
        if parent_locked.estado in _HARD_BLOCK_STATUSES:
            raise SlotNotAvailableError("Parent space is not available for this slot")
        if parent_locked.estado == SlotStatus.BLOCKED_BY_PARENT:
            raise SlotNotAvailableError("Parent space is blocked by a parent reservation")

    # Parent selected: all children must be free.
    locked_child_slots: list[Inventory] = []
    if child_ids:
        for cid in child_ids:
            cslot = _get_or_create_slot(cid, tenant_id, fecha, hora_inicio, hora_fin, db)
            child_locked = db.execute(
                select(Inventory).where(Inventory.id == cslot.id).with_for_update()
            ).scalar_one()
            if child_locked.estado in _HARD_BLOCK_STATUSES:
                raise SlotNotAvailableError("One or more child spaces are not available")
            if child_locked.estado == SlotStatus.BLOCKED_BY_CHILD:
                raise SlotNotAvailableError("One or more child spaces are already blocking the parent")
            locked_child_slots.append(child_locked)

    row.estado = SlotStatus.TTL_BLOCKED
    row.reservation_id = reservation_id

    # Apply relationship blocking for same date/time.
    if parent_id is not None:
        # Child reservation blocks complete parent.
        parent_slot = _get_or_create_slot(
            parent_id, tenant_id, fecha, hora_inicio, hora_fin, db
        )
        parent_locked = db.execute(
            select(Inventory).where(Inventory.id == parent_slot.id).with_for_update()
        ).scalar_one()
        if parent_locked.estado == SlotStatus.AVAILABLE:
            parent_locked.estado = SlotStatus.BLOCKED_BY_CHILD
            parent_locked.reservation_id = None
    else:
        # Parent reservation blocks all children.
        for child_locked in locked_child_slots:
            child_locked.estado = SlotStatus.BLOCKED_BY_PARENT
            child_locked.reservation_id = None

    db.flush()


def release_relationship_blocks_for_reservation_slot(
    space_id: UUID,
    tenant_id: UUID,
    fecha: date,
    hora_inicio: time,
    hora_fin: time,
    db: Session,
) -> None:
    """
    Release parent/child shadow blocks after a reservation slot is cancelled/expired.
    """
    rel_parent = (
        db.query(SpaceRelationship.parent_space_id)
        .filter(
            SpaceRelationship.tenant_id == tenant_id,
            SpaceRelationship.child_space_id == space_id,
        )
        .first()
    )
    rel_children = (
        db.query(SpaceRelationship.child_space_id)
        .filter(
            SpaceRelationship.tenant_id == tenant_id,
            SpaceRelationship.parent_space_id == space_id,
        )
        .all()
    )
    parent_id = rel_parent[0] if rel_parent else None
    child_ids = [r[0] for r in rel_children]

    if parent_id is not None:
        # Child released: unlock parent only if no sibling child remains active.
        sibling_child_ids = [
            r[0]
            for r in (
                db.query(SpaceRelationship.child_space_id)
                .filter(
                    SpaceRelationship.tenant_id == tenant_id,
                    SpaceRelationship.parent_space_id == parent_id,
                )
                .all()
            )
        ]
        sibling_child_rows = (
            db.query(Inventory)
            .filter(
                Inventory.space_id.in_(sibling_child_ids + [space_id]),
                Inventory.tenant_id == tenant_id,
                Inventory.fecha == fecha,
                Inventory.hora_inicio == hora_inicio,
                Inventory.hora_fin == hora_fin,
                Inventory.estado.in_([SlotStatus.TTL_BLOCKED, SlotStatus.RESERVED, SlotStatus.SOFT_HOLD]),
            )
            .all()
        )
        if not sibling_child_rows:
            parent_slot = _get_or_create_slot(
                parent_id, tenant_id, fecha, hora_inicio, hora_fin, db
            )
            parent_locked = db.execute(
                select(Inventory).where(Inventory.id == parent_slot.id).with_for_update()
            ).scalar_one()
            if parent_locked.estado == SlotStatus.BLOCKED_BY_CHILD and parent_locked.reservation_id is None:
                parent_locked.estado = SlotStatus.AVAILABLE
    else:
        # Parent released: children shadow-blocks can be unlocked.
        for cid in child_ids:
            cslot = _get_or_create_slot(cid, tenant_id, fecha, hora_inicio, hora_fin, db)
            child_locked = db.execute(
                select(Inventory).where(Inventory.id == cslot.id).with_for_update()
            ).scalar_one()
            if child_locked.estado == SlotStatus.BLOCKED_BY_PARENT and child_locked.reservation_id is None:
                child_locked.estado = SlotStatus.AVAILABLE
    db.flush()


def would_create_cycle(
    tenant_id: UUID,
    parent_space_id: UUID,
    child_space_id: UUID,
    db: Session,
) -> bool:
    """
    Return True if adding the edge parent_space_id -> child_space_id would create
    a cycle in the space relationship graph (same tenant).
    Self-loop (parent == child) is considered a cycle.
    """
    if parent_space_id == child_space_id:
        return True

    # Build adjacency: from each parent we can go to its children
    rows = (
        db.query(
            SpaceRelationship.parent_space_id,
            SpaceRelationship.child_space_id,
        )
        .filter(SpaceRelationship.tenant_id == tenant_id)
        .all()
    )
    children_of: dict[UUID, list[UUID]] = {}
    for p, c in rows:
        children_of.setdefault(p, []).append(c)

    # BFS from child_space_id: if we reach parent_space_id, then there exists
    # a path child -> ... -> parent, so adding parent -> child would create a cycle
    seen = {child_space_id}
    queue: deque[UUID] = deque([child_space_id])
    while queue:
        node = queue.popleft()
        for next_node in children_of.get(node, []):
            if next_node == parent_space_id:
                return True
            if next_node not in seen:
                seen.add(next_node)
                queue.append(next_node)
    return False


def block_parent_and_children(
    space_id: UUID,
    tenant_id: UUID,
    fecha: date,
    hora_inicio: time,
    hora_fin: time,
    db: Session,
) -> None:
    """
    Block the parent space slot (set to TTL_BLOCKED) and all its children slots
    (set to BLOCKED_BY_PARENT) for the given slot. Uses SELECT FOR UPDATE and
    get-or-create for inventory rows. Call within a transaction (e.g. existing
    request session).
    """
    rels = (
        db.query(SpaceRelationship.child_space_id)
        .filter(
            SpaceRelationship.tenant_id == tenant_id,
            SpaceRelationship.parent_space_id == space_id,
        )
        .all()
    )
    child_ids = [r[0] for r in rels]

    slots: list[Inventory] = []
    parent_slot = _get_or_create_slot(space_id, tenant_id, fecha, hora_inicio, hora_fin, db)
    slots.append(parent_slot)
    for cid in child_ids:
        slots.append(
            _get_or_create_slot(cid, tenant_id, fecha, hora_inicio, hora_fin, db)
        )

    # Lock in deterministic order to avoid deadlock
    slots.sort(key=lambda s: (s.space_id, s.fecha, s.hora_inicio, s.hora_fin))
    ids = [s.id for s in slots]
    stmt = (
        select(Inventory)
        .where(Inventory.id.in_(ids))
        .order_by(Inventory.space_id, Inventory.fecha, Inventory.hora_inicio, Inventory.hora_fin)
        .with_for_update()
    )
    locked = list(db.execute(stmt).scalars().all())
    by_id = {s.id: s for s in locked}

    parent_slot = by_id[parent_slot.id]
    parent_slot.estado = SlotStatus.TTL_BLOCKED
    for cid in child_ids:
        slot = next(s for s in locked if s.space_id == cid)
        slot.estado = SlotStatus.BLOCKED_BY_PARENT
    db.flush()


def block_child_and_parent(
    space_id: UUID,
    tenant_id: UUID,
    fecha: date,
    hora_inicio: time,
    hora_fin: time,
    db: Session,
) -> None:
    """
    Block the child space slot (set to TTL_BLOCKED) and its parent slot
    (set to BLOCKED_BY_CHILD). Uses SELECT FOR UPDATE and get-or-create.
    """
    rel = (
        db.query(SpaceRelationship.parent_space_id)
        .filter(
            SpaceRelationship.tenant_id == tenant_id,
            SpaceRelationship.child_space_id == space_id,
        )
        .first()
    )
    if rel is None:
        # No parent: only block this space
        slot = _get_or_create_slot(space_id, tenant_id, fecha, hora_inicio, hora_fin, db)
        stmt = select(Inventory).where(Inventory.id == slot.id).with_for_update()
        row = db.execute(stmt).scalar_one()
        row.estado = SlotStatus.TTL_BLOCKED
        db.flush()
        return

    parent_id = rel[0]
    child_slot = _get_or_create_slot(space_id, tenant_id, fecha, hora_inicio, hora_fin, db)
    parent_slot = _get_or_create_slot(parent_id, tenant_id, fecha, hora_inicio, hora_fin, db)

    slots = [child_slot, parent_slot]
    slots.sort(key=lambda s: (s.space_id, s.fecha, s.hora_inicio, s.hora_fin))
    ids = [s.id for s in slots]
    stmt = (
        select(Inventory)
        .where(Inventory.id.in_(ids))
        .order_by(Inventory.space_id, Inventory.fecha, Inventory.hora_inicio, Inventory.hora_fin)
        .with_for_update()
    )
    locked = list(db.execute(stmt).scalars().all())
    by_id = {s.id: s for s in locked}
    by_id[child_slot.id].estado = SlotStatus.TTL_BLOCKED
    by_id[parent_slot.id].estado = SlotStatus.BLOCKED_BY_CHILD
    db.flush()


def apply_soft_hold_for_quote(
    quote_id: UUID,
    slots: list[tuple[UUID, date, time, time]],
    tenant_id: UUID,
    db: Session,
) -> None:
    """
    For each (space_id, fecha, hora_inicio, hora_fin), get-or-create slot, lock rows
    in deterministic order, ensure estado == AVAILABLE and reservation_id is None
    and quote_id is None; then set estado = SOFT_HOLD and quote_id = quote_id.
    Raises SlotNotAvailableError if any slot is not available.
    Call within the same transaction as quote creation.
    """
    if not slots:
        return
    # Get or create all slots
    slot_rows: list[Inventory] = []
    for space_id, fecha, hora_inicio, hora_fin in slots:
        slot_rows.append(
            _get_or_create_slot(space_id, tenant_id, fecha, hora_inicio, hora_fin, db)
        )
    # Deterministic order to avoid deadlock
    slot_rows.sort(key=lambda s: (s.space_id, s.fecha, s.hora_inicio, s.hora_fin))
    ids = [s.id for s in slot_rows]
    stmt = (
        select(Inventory)
        .where(Inventory.id.in_(ids))
        .order_by(Inventory.space_id, Inventory.fecha, Inventory.hora_inicio, Inventory.hora_fin)
        .with_for_update()
    )
    locked = list(db.execute(stmt).scalars().all())
    by_id = {row.id: row for row in locked}
    for slot in slot_rows:
        row = by_id[slot.id]
        if (
            row.estado != SlotStatus.AVAILABLE
            or row.reservation_id is not None
            or row.quote_id is not None
        ):
            raise SlotNotAvailableError("Slot is not available for soft hold")
        row.estado = SlotStatus.SOFT_HOLD
        row.quote_id = quote_id
    db.flush()


def release_soft_hold_for_quote(quote_id: UUID, db: Session) -> None:
    """Set all inventory rows with quote_id = quote_id to AVAILABLE and quote_id = NULL."""
    db.query(Inventory).filter(
        Inventory.quote_id == quote_id,
    ).update(
        {
            Inventory.estado: SlotStatus.AVAILABLE,
            Inventory.quote_id: None,
        },
        synchronize_session=False,
    )
    db.flush()


# ---------------------------------------------------------------------------
# FR-03: Availability calendar + check-availability
# ---------------------------------------------------------------------------

# Mapping internal statuses to public-facing calendar statuses
_PUBLIC_STATUS_MAP: dict[SlotStatus, str] = {
    SlotStatus.AVAILABLE: "AVAILABLE",
    SlotStatus.SOFT_HOLD: "TTL_PENDING",
    SlotStatus.TTL_BLOCKED: "TTL_PENDING",
    SlotStatus.RESERVED: "BLOCKED",
    SlotStatus.BLOCKED_BY_PARENT: "BLOCKED",
    SlotStatus.BLOCKED_BY_CHILD: "BLOCKED",
    SlotStatus.MAINTENANCE: "BLOCKED",
}

# Default booking rule when space has no explicit rule
_DEFAULT_ALLOWED_START_TIMES = [f"{h:02d}:00" for h in range(9, 21)]
_DEFAULT_MIN_DURATION = 60


def _get_booking_rule(space_id: UUID, db: Session) -> tuple[int, list[str]]:
    """Return (min_duration_minutes, allowed_start_times) for a space."""
    rule = db.query(SpaceBookingRule).filter(SpaceBookingRule.space_id == space_id).first()
    if rule:
        return rule.min_duration_minutes, rule.allowed_start_times
    return _DEFAULT_MIN_DURATION, _DEFAULT_ALLOWED_START_TIMES


def get_month_availability(
    space_id: UUID,
    year: int,
    month: int,
    db: Session,
    role: str | None = None,
) -> dict:
    """Return month calendar with slots classified by status (CA-01).

    Generates all possible slots from booking rules, then merges with DB state.
    """
    min_duration, allowed_starts = _get_booking_rule(space_id, db)

    # Compute date range for month
    _, last_day = calendar.monthrange(year, month)
    fecha_desde = date(year, month, 1)
    fecha_hasta = date(year, month, last_day)

    # Single DB query for all non-default inventory in the month
    rows = (
        db.query(Inventory)
        .filter(
            Inventory.space_id == space_id,
            Inventory.fecha >= fecha_desde,
            Inventory.fecha <= fecha_hasta,
        )
        .all()
    )
    # Index by (fecha, hora_inicio, hora_fin) for O(1) lookup
    db_slots: dict[tuple[date, time, time], Inventory] = {}
    for row in rows:
        db_slots[(row.fecha, row.hora_inicio, row.hora_fin)] = row

    is_superadmin = role == "SUPERADMIN"

    # Generate all slots and merge
    days: dict[str, list[dict]] = {}
    current = fecha_desde
    while current <= fecha_hasta:
        day_slots = []
        for start_str in allowed_starts:
            parts = start_str.split(":")
            hora_inicio = time(int(parts[0]), int(parts[1]))
            end_minutes = int(parts[0]) * 60 + int(parts[1]) + min_duration
            hora_fin = time(end_minutes // 60, end_minutes % 60)

            key = (current, hora_inicio, hora_fin)
            inv = db_slots.get(key)

            if inv is None:
                derived = _derived_relationship_block(
                    space_id, current, hora_inicio, hora_fin, db
                )
                if derived is None:
                    status = "AVAILABLE"
                else:
                    status = _PUBLIC_STATUS_MAP.get(derived, "BLOCKED")
            else:
                # CA-06: MAINTENANCE shows as BLOCKED for non-superadmin
                if inv.estado == SlotStatus.MAINTENANCE and is_superadmin:
                    status = "MAINTENANCE"
                else:
                    if inv.estado == SlotStatus.AVAILABLE:
                        derived = _derived_relationship_block(
                            space_id, current, hora_inicio, hora_fin, db
                        )
                        status = (
                            _PUBLIC_STATUS_MAP.get(derived, "AVAILABLE")
                            if derived is not None
                            else "AVAILABLE"
                        )
                    else:
                        status = _PUBLIC_STATUS_MAP.get(inv.estado, "BLOCKED")

            day_slots.append({
                "fecha": current.isoformat(),
                "hora_inicio": hora_inicio.strftime("%H:%M:%S"),
                "hora_fin": hora_fin.strftime("%H:%M:%S"),
                "status": status,
            })
        days[current.isoformat()] = day_slots
        current += timedelta(days=1)

    return {"month": f"{year:04d}-{month:02d}", "days": days}


def check_single_availability(
    space_id: UUID,
    fecha: date,
    hora_inicio: time,
    hora_fin: time,
    db: Session,
    role: str | None = None,
) -> dict:
    """Check availability for a single slot (CA-02).

    Returns dict with available, estado, motivo, and optionally allowed_blocks.
    """
    # Validate granularity against booking rules
    min_duration, allowed_starts = _get_booking_rule(space_id, db)
    start_str = hora_inicio.strftime("%H:%M")
    if start_str not in allowed_starts:
        return {
            "available": False,
            "estado": "INVALID_SLOT_GRANULARITY",
            "motivo": f"La hora de inicio {start_str} no es válida para este espacio.",
            "allowed_blocks": allowed_starts,
        }
    requested_minutes = (hora_fin.hour * 60 + hora_fin.minute) - (hora_inicio.hour * 60 + hora_inicio.minute)
    if requested_minutes < min_duration:
        return {
            "available": False,
            "estado": "INVALID_SLOT_GRANULARITY",
            "motivo": f"La duración mínima es {min_duration} minutos.",
            "allowed_blocks": allowed_starts,
        }

    # Query inventory for exact slot
    row = (
        db.query(Inventory)
        .filter(
            Inventory.space_id == space_id,
            Inventory.fecha == fecha,
            Inventory.hora_inicio == hora_inicio,
            Inventory.hora_fin == hora_fin,
        )
        .first()
    )

    if row is None or row.estado == SlotStatus.AVAILABLE:
        derived = _derived_relationship_block(space_id, fecha, hora_inicio, hora_fin, db)
        if derived is None:
            return {"available": True, "estado": "AVAILABLE", "motivo": "Disponible"}
        row_status = derived
    else:
        row_status = row.estado

    # Map status for public
    is_privileged = role in ("COMMERCIAL", "SUPERADMIN")
    public_status = _PUBLIC_STATUS_MAP.get(row_status, "BLOCKED")

    # CA-04: differentiated motivo by role
    if is_privileged:
        motivo = f"Estado interno: {row_status.value}"
        if row is not None and row.reservation_id:
            motivo += f" (reserva {row.reservation_id})"
        if row is not None and row.quote_id:
            motivo += f" (cotización {row.quote_id})"
    else:
        motivo = "Este espacio no está disponible en el horario seleccionado"

    # CA-06: MAINTENANCE hidden for non-superadmin
    if row_status == SlotStatus.MAINTENANCE and role != "SUPERADMIN":
        public_status = "BLOCKED"

    return {"available": False, "estado": public_status, "motivo": motivo}


def check_group_availability(
    items: list[dict],
    db: Session,
    role: str | None = None,
) -> dict:
    """Check availability for a group of slots (CA-03, for EventCart).

    items: list of {espacio_id, fecha, hora_inicio, hora_fin}
    """
    conflicts = []
    all_available = True

    for item in items:
        result = check_single_availability(
            space_id=item["espacio_id"],
            fecha=item["fecha"],
            hora_inicio=item["hora_inicio"],
            hora_fin=item["hora_fin"],
            db=db,
            role=role,
        )
        if not result["available"]:
            all_available = False
            conflicts.append({
                "espacio_id": item["espacio_id"],
                "estado": result["estado"],
                "motivo": result["motivo"],
            })

    return {"all_available": all_available, "conflicts": conflicts}
