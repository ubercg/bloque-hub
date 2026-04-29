"""PDF de precotización para reservas del portal (cliente), sin pasar por CRM Quote."""

from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path
import urllib.request
from uuid import UUID

from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session
from weasyprint import HTML

from app.modules.booking.event_summary import space_name_map
from app.modules.booking.models import Reservation
from app.modules.booking.order_table_rows import (
    build_precotizacion_order_context,
    format_mxn_display,
    format_qty_display,
    format_fechas_evento_spanish,
)
from app.modules.inventory.models import Space

_ASSETS_DIR = Path(__file__).parent / "templates" / "assets"


def _asset_file_uri(filename: str) -> str:
    """URI file:// para WeasyPrint (logos en templates/assets)."""
    path = (_ASSETS_DIR / filename).resolve()
    if not path.is_file():
        return ""
    return path.as_uri()


def _frontend_public_file_uri(filename: str) -> str:
    """URI para WeasyPrint con imágenes en `src/frontend/public`.

    En Docker el backend no siempre monta `src/frontend/public`, así que primero buscamos
    en el filesystem local y, si no existe, devolvemos una URL interna (`frontend:3000`)
    para que WeasyPrint intente cargarla.
    """
    file_path_candidates: list[Path] = []
    resolved = Path(__file__).resolve()
    for parent in [resolved.parent, *resolved.parents]:
        file_path_candidates.append(parent / "src" / "frontend" / "public" / filename)

    for p in file_path_candidates:
        try:
            if p.is_file():
                return p.resolve().as_uri()
        except OSError:
            # Some environments may block filesystem access; fall back.
            pass

    # Docker-network fallback: descargar nosotros y embebérselo a WeasyPrint como data URI.
    # Esto evita el caso en que WeasyPrint no pueda hacer fetch remoto directamente.
    if filename in {"header_cot.jpg", "footer_cot.jpg"}:
        try:
            url = f"http://frontend:3000/{filename}"
            with urllib.request.urlopen(url, timeout=8) as resp:
                data = resp.read()
            b64 = base64.b64encode(data).decode("ascii")
            return f"data:image/jpeg;base64,{b64}"
        except Exception:
            pass

    # Best-effort remota (por si WeasyPrint sí puede cargarla).
    return f"http://frontend:3000/{filename}"


def generate_event_precotizacion_pdf_bytes(
    db: Session,
    tenant_id: UUID,
    reservations: list[Reservation],
    *,
    client_name: str,
    client_email: str,
) -> bytes:
    if not reservations:
        raise ValueError("No reservations")

    first = reservations[0]
    event_name = first.event_name or f"Evento {str(first.id)[:8].upper()}"
    document_ref = str(first.group_event_id or first.id)

    logo_bloque_uri = _asset_file_uri("logo-bloque.svg")
    logo_footer_mun_uri = _asset_file_uri("logo-footer-munbloque.png")
    # Encabezado y pie del PDF (assets del backend para WeasyPrint)
    header_cot_uri = _asset_file_uri("header_cot.jpg")
    footer_cot_uri = _asset_file_uri("footer_cot.jpg")

    def _fmt_mxn_space(n: float) -> str:
        """Formato de moneda con espacio después del símbolo ($ 345,737)."""
        return format_mxn_display(n).replace("$", "$ ")

    def _format_time_12h(t) -> str:
        hour24 = int(getattr(t, "hour", 0))
        minute = int(getattr(t, "minute", 0))
        ampm = "am" if hour24 < 12 else "pm"
        hour12 = hour24 % 12
        if hour12 == 0:
            hour12 = 12
        return f"{hour12}:{minute:02d} {ampm}"

    def _render_tiempo_label(raw: str) -> str:
        s = (raw or "").strip().lower()
        if s == "por hora":
            return "POR HORA"
        if s.endswith("horas") and not s.startswith("por"):
            # "6 horas" / "12 horas" -> "POR 6 HORAS"
            return f"POR {s.replace(' horas', '').strip()} HORAS"
        return (raw or "").strip().upper()

    sids = {r.space_id for r in reservations}
    names = space_name_map(db, tenant_id, sids)
    fallback_hourly: dict[UUID, float] = {}
    spaces = db.query(Space).filter(Space.id.in_(sids)).all()
    for row in spaces:
        fallback_hourly[row.id] = float(row.precio_por_hora or 0)

    # Campos de cabecera (para que el PDF coincida con el formato del screenshot)
    dates = sorted({r.fecha for r in reservations})
    # Fecha mostrada junto a "Fecha:" = momento de generación/impresión del PDF (no fecha de reserva)
    now = datetime.now()
    quote_fecha = format_fechas_evento_spanish([now.date()])
    event_dates_span = format_fechas_evento_spanish(dates) if dates else "—"
    event_dates_span = f"{event_dates_span}." if event_dates_span != "—" else "—"

    horario = (
        f"{_format_time_12h(first.hora_inicio)} a {_format_time_12h(first.hora_fin)}."
        if first.hora_inicio and first.hora_fin
        else "—"
    )

    # "Aforo" (fallback): usamos la capacidad máxima entre espacios del evento.
    caps = [int(getattr(s, "capacidad_maxima", 0) or 0) for s in spaces]
    aforo_personas = max(caps) if caps else 0

    rows, subtotal, discount_total, discount_code, grand_total = build_precotizacion_order_context(
        db,
        tenant_id,
        reservations,
        names,
        fallback_hourly,
    )

    order_rows_display = []
    for row in rows:
        order_rows_display.append(
            {
                "espacio": row.espacio,
                "tiempo": _render_tiempo_label(row.tiempo_label),
                "precio_unitario": _fmt_mxn_space(float(row.precio_unitario)),
                "cantidad": format_qty_display(row.cantidad),
                "total": _fmt_mxn_space(float(row.total)),
            }
        )

    discount_percent = 0
    if subtotal and subtotal > 0 and discount_total and discount_total > 0:
        # redondeo para mostrar "Descuento 75%" como en el screenshot
        discount_percent = int(round((float(discount_total) / float(subtotal)) * 100))
        discount_percent = max(0, min(100, discount_percent))

    templates_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(templates_dir)))
    template = env.get_template("precotizacion_event_template.html")
    html = template.render(
        event_name=event_name,
        document_ref=document_ref,
        generated_at=now.strftime("%Y-%m-%d %H:%M"),
        client_name=client_name,
        client_email=client_email,
        order_rows=order_rows_display,
        discount_code=discount_code,
        has_discount=discount_total > 0,
        quote_fecha=quote_fecha,
        event_dates_span=event_dates_span,
        horario=horario,
        aforo_personas=aforo_personas,
        subtotal=_fmt_mxn_space(float(subtotal)),
        discount_percent=discount_percent,
        discount_amount=_fmt_mxn_space(float(discount_total)) if discount_total > 0 else _fmt_mxn_space(0.0),
        grand_total=_fmt_mxn_space(float(grand_total)),
        logo_bloque_uri=logo_bloque_uri,
        logo_footer_mun_uri=logo_footer_mun_uri,
        header_cot_uri=header_cot_uri,
        footer_cot_uri=footer_cot_uri,
    )
    return HTML(string=html).write_pdf()
