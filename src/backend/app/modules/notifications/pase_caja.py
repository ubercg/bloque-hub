"""Contexto y render HTML del correo Pase de Caja (reutilizable por API preview y Celery)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.booking.event_summary import (
    compute_precotizacion_line_items,
    list_reservations_for_event,
    space_name_map,
)
from app.modules.booking.models import Reservation
from app.modules.identity.models import User
from app.modules.inventory.models import Space
from app.modules.notifications.templating import render


def _fmt_time(t) -> str:
    if t is None:
        return ""
    return t.strftime("%H:%M") if hasattr(t, "strftime") else str(t)


def _fmt_date(d) -> str:
    if d is None:
        return ""
    return d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)


def _base_context(reservation: Reservation, user: User | None, space: Space | None) -> dict:
    portal = settings.PORTAL_BASE_URL.rstrip("/")
    link_portal = f"{portal}/reservations/{reservation.id}" if reservation else portal
    link_upload_slip = f"{portal}/reservations/{reservation.id}/upload-slip" if reservation else None
    customer_name = (user.full_name if user else "") or "Cliente"
    space_name = (space.name if space else "") or "Espacio"
    fecha = _fmt_date(reservation.fecha) if reservation else ""
    hora_inicio = _fmt_time(reservation.hora_inicio) if reservation else ""
    hora_fin = _fmt_time(reservation.hora_fin) if reservation else ""
    folio = str(reservation.id) if reservation else ""
    return {
        "customer_name": customer_name,
        "space_name": space_name,
        "fecha": fecha,
        "hora_inicio": hora_inicio,
        "hora_fin": hora_fin,
        "folio": folio,
        "link_portal": link_portal,
        "link_upload_slip": link_upload_slip,
    }


def build_pase_de_caja_event_context(
    db: Session,
    anchor_reservation_id: UUID,
    included_reservation_ids: list[UUID] | None,
) -> dict | None:
    """
    Contexto para un correo de Pase de Caja.

    - `included_reservation_ids` None: todas las reservas del mismo evento que la ancla.
    - Lista explícita: solo esas filas (p. ej. bulk solo slots PENDING_SLIP).
    """
    anchor = db.get(Reservation, anchor_reservation_id)
    if anchor is None:
        return None
    tenant_id = anchor.tenant_id
    all_rows = list_reservations_for_event(db, tenant_id, anchor)
    if included_reservation_ids is not None:
        id_set = set(included_reservation_ids)
        rows = [r for r in all_rows if r.id in id_set]
    else:
        rows = list(all_rows)
    if not rows:
        return None
    user = db.get(User, anchor.user_id)

    clabe = getattr(settings, "SPEI_CLABE", None) or "—"
    banco = getattr(settings, "SPEI_BANCO", None) or "—"
    prefix = getattr(settings, "SPEI_REFERENCE_PREFIX", "") or ""
    ref_key = anchor.group_event_id if anchor.group_event_id is not None else anchor.id
    referencia_spei = prefix + "-" + str(ref_key).replace("-", "")[:8]

    if len(rows) == 1:
        r = rows[0]
        space = db.get(Space, r.space_id)
        ctx = _base_context(r, user, space)
        ctx["monto"] = f"${space.precio_por_hora:,.2f}" if space else "Consultar"
        ctx["clabe"] = clabe
        ctx["referencia_spei"] = prefix + "-" + str(r.id)[:8]
        ctx["banco"] = banco
        ctx["is_multi_slot"] = False
        return ctx

    lines_raw, subtotal = compute_precotizacion_line_items(db, tenant_id, rows)
    names = space_name_map(db, tenant_id, {r.space_id for r in rows})
    line_rows: list[dict] = []
    for ln in lines_raw:
        sid = ln["space_id"]
        line_rows.append(
            {
                "space_name": names.get(sid, "Espacio"),
                "fecha": _fmt_date(ln["fecha"]),
                "hora_inicio": _fmt_time(ln["hora_inicio"]),
                "hora_fin": _fmt_time(ln["hora_fin"]),
                "precio_fmt": f"${Decimal(str(ln['precio'])):,.2f}",
            }
        )
    first = min(rows, key=lambda x: (x.fecha, x.hora_inicio, x.id))
    portal = settings.PORTAL_BASE_URL.rstrip("/")
    return {
        "is_multi_slot": True,
        "customer_name": (user.full_name if user else "") or "Cliente",
        "lines": line_rows,
        "monto_total": f"${subtotal:,.2f}",
        "clabe": clabe,
        "referencia_spei": referencia_spei,
        "banco": banco,
        "link_portal": f"{portal}/my-events/{first.id}",
        "link_upload_slip": f"{portal}/reservations/{first.id}/upload-slip",
        "folio_evento": str(ref_key),
    }


def build_pase_de_caja_context(db: Session, reservation_id: UUID) -> dict | None:
    """Una reserva (p. ej. POST /reservations/{id}/generate_slip): solo ese slot en el correo."""
    r = db.get(Reservation, reservation_id)
    if r is None:
        return None
    return build_pase_de_caja_event_context(db, reservation_id, [reservation_id])


def render_pase_de_caja_email_html(ctx: dict) -> str:
    if ctx.get("is_multi_slot"):
        return render("pase_de_caja_emitido_evento.html", **ctx)
    return render("pase_de_caja_emitido.html", **ctx)
