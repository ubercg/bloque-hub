"""Tests unitarios de render de plantillas Jinja2 (notificaciones)."""

import pytest

from app.modules.notifications.templating import render


def test_render_pre_reserva_iniciada() -> None:
    html = render(
        "pre_reserva_iniciada.html",
        customer_name="Juan Pérez",
        space_name="Sala A",
        fecha="2025-03-15",
        hora_inicio="09:00",
        hora_fin="13:00",
    )
    assert "Juan Pérez" in html
    assert "Sala A" in html
    assert "2025-03-15" in html
    assert "09:00" in html and "13:00" in html
    assert "bloqueado" in html.lower() or "24" in html


def test_render_pre_reserva_comercial() -> None:
    html = render(
        "pre_reserva_comercial.html",
        customer_name="María",
        customer_email="maria@example.com",
        space_name="Auditorio",
        fecha="2025-03-20",
        hora_inicio="14:00",
        hora_fin="18:00",
        monto="$1,500",
        folio="R-001",
    )
    assert "María" in html and "maria@example.com" in html
    assert "Auditorio" in html
    assert "R-001" in html
    assert "1,500" in html


def test_render_pase_de_caja_emitido() -> None:
    html = render(
        "pase_de_caja_emitido.html",
        customer_name="Ana",
        space_name="Sala B",
        folio="R-002",
        monto="$2,000",
        fecha="2025-04-01",
        hora_inicio="10:00",
        hora_fin="12:00",
        clabe="012180012345678901",
        referencia_spei="REF123",
        banco="Banco Ejemplo",
    )
    assert "Ana" in html and "Sala B" in html
    assert "R-002" in html and "2,000" in html
    assert "012180012345678901" in html and "REF123" in html


def test_render_pase_de_caja_optional_links() -> None:
    """Variables opcionales link_upload_slip y link_portal no rompen la plantilla."""
    html = render(
        "pase_de_caja_emitido.html",
        customer_name="X",
        space_name="Y",
        folio="F",
        monto="0",
        fecha="2025-01-01",
        hora_inicio="00:00",
        hora_fin="01:00",
        clabe="0",
        referencia_spei="0",
        banco="B",
    )
    assert "X" in html


def test_render_recordatorio_ttl() -> None:
    html = render(
        "recordatorio_ttl.html",
        customer_name="Carlos",
        space_name="Sala C",
        ttl_expires_at="2025-03-10 18:00",
    )
    assert "Carlos" in html and "Sala C" in html
    assert "4 horas" in html or "expira" in html.lower()
    assert "2025-03-10" in html or "18:00" in html


def test_render_confirmacion_con_qr() -> None:
    html = render(
        "confirmacion_con_qr.html",
        customer_name="Laura",
        space_name="Sala VIP",
        fecha="2025-05-01",
        hora_inicio="09:00",
        hora_fin="17:00",
        link_portal="https://portal.example.com",
    )
    assert "Laura" in html and "Sala VIP" in html
    assert "confirmada" in html.lower()
    assert "https://portal.example.com" in html


def test_render_confirmacion_sin_link_qr() -> None:
    """Sin link_download_qr la plantilla usa solo link_portal si existe."""
    html = render(
        "confirmacion_con_qr.html",
        customer_name="Test",
        space_name="Espacio",
        fecha="2025-01-01",
        hora_inicio="00:00",
        hora_fin="01:00",
    )
    assert "Test" in html and "confirmada" in html.lower()
