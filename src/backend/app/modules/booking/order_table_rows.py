"""
Filas tipo «Detalle de Espacios» (misma lógica que confirm-summary.ts / buildOrderTableRows).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.booking.models import Reservation
from app.modules.discounts.services import compute_discount_amount
from app.modules.pricing.services import get_pricing_rule_by_space, get_quote_for_space

EPS = 1e-6
HOURS_PER_MONTH_PACKAGE = 30 * 24
HOURS_PER_WEEK_PACKAGE = 5 * 24
MAX_MONTH_PACKAGES = 11

MONTHS_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


@dataclass
class CatalogPrices:
    por_hora: float
    seis_horas: float
    doce_horas: float
    semana: float = 0.0
    mes: float = 0.0


@dataclass
class CartItem:
    space_id: UUID
    space_name: str
    fecha: date
    hora_inicio: str  # HH:MM
    hora_fin: str
    precio: int


@dataclass
class MergedTimeBlock:
    fecha: date
    hora_inicio: str
    hora_fin: str
    precio_total: int


@dataclass
class PackageSegment:
    kind: str
    label: str
    qty: float
    unit_catalog: float


@dataclass
class OrderTableRow:
    key: str
    espacio: str
    tiempo_label: str
    precio_unitario: int
    cantidad: float
    total: int


def _time_to_minutes(t: str) -> int:
    parts = t.split(":")
    h = int(parts[0]) if parts else 0
    m = int(parts[1]) if len(parts) > 1 else 0
    return h * 60 + m


def slot_duration_hours(hora_inicio: str, hora_fin: str) -> float:
    a = _time_to_minutes(hora_inicio)
    b = _time_to_minutes(hora_fin)
    diff = b - a
    if diff <= 0:
        return 1.0
    return diff / 60.0


def merge_contiguous_blocks(items: list[CartItem]) -> list[MergedTimeBlock]:
    by_date: dict[date, list[CartItem]] = {}
    for it in items:
        by_date.setdefault(it.fecha, []).append(it)

    out: list[MergedTimeBlock] = []
    for fecha, arr in by_date.items():
        arr.sort(key=lambda x: (x.hora_inicio, x.hora_fin))
        current: MergedTimeBlock | None = None
        for it in arr:
            if current is None:
                current = MergedTimeBlock(
                    fecha=fecha,
                    hora_inicio=it.hora_inicio,
                    hora_fin=it.hora_fin,
                    precio_total=it.precio,
                )
                continue
            if _time_to_minutes(it.hora_inicio) == _time_to_minutes(current.hora_fin):
                current.hora_fin = it.hora_fin
                current.precio_total += it.precio
            else:
                out.append(current)
                current = MergedTimeBlock(
                    fecha=fecha,
                    hora_inicio=it.hora_inicio,
                    hora_fin=it.hora_fin,
                    precio_total=it.precio,
                )
        if current:
            out.append(current)

    out.sort(key=lambda b: (b.fecha, b.hora_inicio))
    return out


def decompose_hours_into_packages(total_hours: float, prices: CatalogPrices) -> list[PackageSegment]:
    out: list[PackageSegment] = []
    h = max(0.0, total_hours)

    if prices.mes > 0:
        n = min(int(h / HOURS_PER_MONTH_PACKAGE + EPS), MAX_MONTH_PACKAGES)
        if n > 0:
            out.append(PackageSegment(kind="mes", label="mes", qty=float(n), unit_catalog=prices.mes))
            h -= n * HOURS_PER_MONTH_PACKAGE

    if prices.semana > 0:
        n = int(h / HOURS_PER_WEEK_PACKAGE + EPS)
        if n > 0:
            out.append(
                PackageSegment(kind="semana", label="semana (5 días)", qty=float(n), unit_catalog=prices.semana)
            )
            h -= n * HOURS_PER_WEEK_PACKAGE

    if prices.doce_horas > 0:
        n12 = int(h / 12 + EPS)
        if n12 > 0:
            out.append(PackageSegment(kind="h12", label="12 horas", qty=float(n12), unit_catalog=prices.doce_horas))
            h -= n12 * 12

    if prices.seis_horas > 0:
        n6 = int(h / 6 + EPS)
        if n6 > 0:
            out.append(PackageSegment(kind="h6", label="6 horas", qty=float(n6), unit_catalog=prices.seis_horas))
            h -= n6 * 6

    if h > EPS and prices.por_hora > 0:
        out.append(PackageSegment(kind="hora", label="por hora", qty=h, unit_catalog=prices.por_hora))

    return out


def decompose_hours_by_time_only(total_hours: float) -> list[PackageSegment]:
    out: list[PackageSegment] = []
    h = max(0.0, total_hours)
    n12 = int(h / 12 + EPS)
    if n12 > 0:
        out.append(PackageSegment(kind="h12", label="12 horas", qty=float(n12), unit_catalog=0.0))
        h -= n12 * 12
    n6 = int(h / 6 + EPS)
    if n6 > 0:
        out.append(PackageSegment(kind="h6", label="6 horas", qty=float(n6), unit_catalog=0.0))
        h -= n6 * 6
    if h > EPS:
        out.append(PackageSegment(kind="hora", label="por hora", qty=h, unit_catalog=0.0))
    return out


def allocate_totals_mxn(total: int, weights: list[float]) -> list[int]:
    if not weights:
        return []
    sum_w = sum(weights)
    if sum_w <= 0:
        return [0] * len(weights)
    n = len(weights)
    out: list[int] = []
    acc = 0
    for i in range(n - 1):
        t = round((total * weights[i]) / sum_w)
        out.append(int(t))
        acc += int(t)
    out.append(total - acc)
    return out


def get_segment_unit_price_from_pricing(seg: PackageSegment, prices: CatalogPrices) -> int:
    if seg.kind == "mes":
        if (prices.mes or 0) > 0:
            return int(round(prices.mes))
        return int(round((prices.por_hora or 0) * HOURS_PER_MONTH_PACKAGE))
    if seg.kind == "semana":
        if (prices.semana or 0) > 0:
            return int(round(prices.semana))
        return int(round((prices.por_hora or 0) * HOURS_PER_WEEK_PACKAGE))
    if seg.kind == "h12":
        if (prices.doce_horas or 0) > 0:
            return int(round(prices.doce_horas))
        if (prices.seis_horas or 0) > 0:
            return int(round(prices.seis_horas * 2))
        return int(round((prices.por_hora or 0) * 12))
    if seg.kind == "h6":
        if (prices.seis_horas or 0) > 0:
            return int(round(prices.seis_horas))
        return int(round((prices.por_hora or 0) * 6))
    return int(round(prices.por_hora or 0))


def format_fechas_evento_spanish(dates_iso: list[date]) -> str:
    sorted_dates = sorted(set(dates_iso))
    if not sorted_dates:
        return "—"
    if len(sorted_dates) == 1:
        d = sorted_dates[0]
        return f"{d.day} de {MONTHS_ES[d.month - 1]} de {d.year}"
    y0 = sorted_dates[0].year
    same_year = all(d.year == y0 for d in sorted_dates)
    m0 = sorted_dates[0].month
    same_month = all(d.month == m0 for d in sorted_dates)
    if same_year and same_month:
        month = MONTHS_ES[m0 - 1]
        days = [d.day for d in sorted_dates]
        if len(days) == 2:
            return f"{days[0]} y {days[1]} de {month} de {y0}"
        last = days[-1]
        rest = days[:-1]
        return f"{', '.join(str(x) for x in rest)} y {last} de {month} de {y0}"
    return "; ".join(f"{d.day} de {MONTHS_ES[d.month - 1]} de {d.year}" for d in sorted_dates)


def group_cart_items_by_space_for_reservation_period(items: list[CartItem]) -> list[dict]:
    m: dict[UUID, list[CartItem]] = {}
    for it in items:
        m.setdefault(it.space_id, []).append(it)
    for arr in m.values():
        arr.sort(key=lambda x: (x.fecha, x.hora_inicio))
    groups: list[dict] = []
    for space_id, group_items in sorted(m.items(), key=lambda x: (x[1][0].space_name if x[1] else "", str(x[0]))):
        groups.append(
            {
                "key": str(space_id),
                "space_id": space_id,
                "space_name": group_items[0].space_name,
                "fecha": group_items[0].fecha,
                "items": group_items,
            }
        )
    return groups


def build_order_table_rows(
    items: list[CartItem],
    pricing_by_space_id: dict[UUID, CatalogPrices],
) -> list[OrderTableRow]:
    out: list[OrderTableRow] = []
    groups = group_cart_items_by_space_for_reservation_period(items)

    for g in groups:
        space_id = g["space_id"]
        space_name = g["space_name"]
        prices = pricing_by_space_id.get(space_id)
        by_time: dict[str, OrderTableRow] = {}
        row_dates: dict[str, set[date]] = {}
        merged_blocks = merge_contiguous_blocks(g["items"])

        for block in merged_blocks:
            hours = slot_duration_hours(block.hora_inicio, block.hora_fin)
            total_precio = int(round(block.precio_total))

            segments: list[PackageSegment] = []
            if prices:
                has_pkg = (prices.doce_horas or 0) > 0 or (prices.seis_horas or 0) > 0
                segments = (
                    decompose_hours_into_packages(hours, prices)
                    if has_pkg
                    else decompose_hours_by_time_only(hours)
                )
            else:
                segments = decompose_hours_by_time_only(hours)

            if not segments:
                segments = [PackageSegment(kind="hora", label="por hora", qty=max(hours, 1.0), unit_catalog=1.0)]

            if prices:
                seg_totals = [
                    int(
                        round(
                            get_segment_unit_price_from_pricing(seg, prices) * seg.qty,
                        )
                    )
                    for seg in segments
                ]
            else:
                seg_totals = allocate_totals_mxn(total_precio, [s.qty for s in segments])

            for idx, seg in enumerate(segments):
                seg_total = seg_totals[idx] if idx < len(seg_totals) else 0
                tiempo_label = (
                    "mes"
                    if seg.kind == "mes"
                    else "semana (5 días)"
                    if seg.kind == "semana"
                    else "12 horas"
                    if seg.kind == "h12"
                    else "6 horas"
                    if seg.kind == "h6"
                    else "por hora"
                )
                qty = max(seg.qty, 0.0) if seg.kind == "hora" else max(seg.qty, 0.0)
                rounded_qty = round(qty * 100) / 100
                if prices:
                    unit_price = int(round(get_segment_unit_price_from_pricing(seg, prices)))
                else:
                    unit_price = int(round(seg_total / rounded_qty)) if rounded_qty > EPS else seg_total

                aggregate_across_event = seg.kind != "hora"
                k = (
                    f"{space_id}|{tiempo_label}|{unit_price}"
                    if aggregate_across_event
                    else f"{space_id}|{block.fecha}|{tiempo_label}|{unit_price}"
                )
                prev = by_time.get(k)
                if not prev:
                    by_time[k] = OrderTableRow(
                        key=f"{g['key']}|{k}",
                        espacio=space_name,
                        tiempo_label=tiempo_label,
                        precio_unitario=unit_price,
                        cantidad=rounded_qty,
                        total=seg_total,
                    )
                    row_dates[k] = {block.fecha}
                else:
                    prev.cantidad = round((prev.cantidad + rounded_qty) * 100) / 100
                    prev.total += seg_total
                    if prev.cantidad > EPS:
                        prev.precio_unitario = int(round(prev.total / prev.cantidad))
                    row_dates.setdefault(k, set()).add(block.fecha)

        def rank(label: str) -> int:
            if label == "mes":
                return 0
            if label == "semana (5 días)":
                return 1
            if label == "12 horas":
                return 2
            if label == "6 horas":
                return 3
            return 4

        keyed_rows: list[tuple[OrderTableRow, str]] = []
        for k, row in by_time.items():
            dates = sorted(row_dates.get(k, set()))
            if dates:
                row.espacio = f"{space_name} ({format_fechas_evento_spanish(dates)})"
            first_date = dates[0].isoformat() if dates else "9999-12-31"
            keyed_rows.append((row, first_date))

        keyed_rows.sort(key=lambda x: (x[1], rank(x[0].tiempo_label), x[0].tiempo_label))
        out.extend(r for r, _ in keyed_rows)

    return out


def catalog_prices_for_space(
    db: Session,
    tenant_id: UUID,
    space_id: UUID,
    target_date: date,
    fallback_por_hora: float,
) -> CatalogPrices:
    rule = get_pricing_rule_by_space(db, tenant_id, space_id, target_date)
    if rule:
        return CatalogPrices(
            por_hora=float(rule.extra_hour_rate),
            seis_horas=float(rule.base_6h),
            doce_horas=float(rule.base_12h),
            semana=0.0,
            mes=0.0,
        )
    return CatalogPrices(
        por_hora=fallback_por_hora,
        seis_horas=0.0,
        doce_horas=0.0,
    )


def reservations_to_cart_items(
    db: Session,
    tenant_id: UUID,
    reservations: list[Reservation],
    space_names: dict[UUID, str],
) -> list[CartItem]:
    items: list[CartItem] = []
    for r in reservations:
        dur = _slot_duration_hours_res(r.hora_inicio, r.hora_fin)
        q = get_quote_for_space(
            db=db,
            tenant_id=tenant_id,
            space_id=r.space_id,
            target_date=r.fecha,
            duration_hours=dur,
        )
        precio = int(round(float(q["total_price"])))
        name = space_names.get(r.space_id, str(r.space_id))
        items.append(
            CartItem(
                space_id=r.space_id,
                space_name=name,
                fecha=r.fecha,
                hora_inicio=r.hora_inicio.strftime("%H:%M"),
                hora_fin=r.hora_fin.strftime("%H:%M"),
                precio=precio,
            )
        )
    return items


def _slot_duration_hours_res(hora_inicio: time, hora_fin: time) -> Decimal:
    start_minutes = hora_inicio.hour * 60 + hora_inicio.minute
    end_minutes = hora_fin.hour * 60 + hora_fin.minute
    diff = max(0, end_minutes - start_minutes)
    return (Decimal(diff) / Decimal(60)).quantize(Decimal("0.01"))


def build_precotizacion_order_context(
    db: Session,
    tenant_id: UUID,
    reservations: list[Reservation],
    space_names: dict[UUID, str],
    space_fallback_hourly: dict[UUID, float],
) -> tuple[list[OrderTableRow], int, float, str | None, float]:
    """
    Retorna: rows, subtotal (int), discount_total (float), discount_code (optional), grand_total (float).
    """
    if not reservations:
        return [], 0, 0.0, None, 0.0

    ref_date = min(r.fecha for r in reservations)
    pricing_by_space: dict[UUID, CatalogPrices] = {}
    for sid in {r.space_id for r in reservations}:
        pricing_by_space[sid] = catalog_prices_for_space(
            db, tenant_id, sid, ref_date, space_fallback_hourly.get(sid, 0.0)
        )

    cart = reservations_to_cart_items(db, tenant_id, reservations, space_names)
    rows = build_order_table_rows(cart, pricing_by_space)
    subtotal = sum(r.total for r in rows)
    # Subtotal alineado al «Detalle de Espacios» (paquetes); puede diferir del subtotal por slot
    # usado al crear la reserva. El descuento debe recalcularse sobre ESTE subtotal con la misma
    # regla que validate_code / pantalla de confirmación.
    subtotal_dec = Decimal(str(subtotal))

    discount_code: str | None = None
    discount_total = Decimal("0.00")
    did = reservations[0].discount_code_id
    if did is not None:
        from app.modules.discounts.models import DiscountCode

        dc = db.query(DiscountCode).filter(DiscountCode.id == did, DiscountCode.tenant_id == tenant_id).first()
        if dc:
            discount_code = dc.code
            discount_total = compute_discount_amount(
                subtotal_dec,
                dc.discount_type,
                Decimal(str(dc.discount_value)),
            )
        else:
            for r in reservations:
                if r.discount_amount_applied is not None:
                    discount_total += Decimal(str(r.discount_amount_applied))
    else:
        for r in reservations:
            if r.discount_amount_applied is not None:
                discount_total += Decimal(str(r.discount_amount_applied))

    discount_f = float(discount_total.quantize(Decimal("0.01")))
    grand_total = max(0.0, float(subtotal_dec) - discount_f)
    return rows, subtotal, discount_f, discount_code, grand_total


def format_qty_display(qty: float) -> str:
    if abs(qty - round(qty)) < 1e-4:
        return str(int(round(qty)))
    s = f"{qty:.2f}"
    return s.replace(".", ",")


def format_mxn_display(n: float) -> str:
    """Miles con coma, alineado a pantalla de confirmación."""
    if abs(n - round(n)) < 0.05:
        return f"${int(round(n)):,}"
    return f"${n:,.1f}"
