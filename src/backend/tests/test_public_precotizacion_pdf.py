"""Public wizard precotización PDF endpoint (REQ-012 Step 5)."""

from unittest.mock import patch
from uuid import uuid4

import pytest

from app.core.config import settings
from app.modules.inventory.models import Space


def _set_default_tenant(monkeypatch, tenant_id):
    monkeypatch.setattr(settings, "DEFAULT_TENANT_ID", str(tenant_id))


def _make_space(db_super, tenant_id, suffix: str) -> Space:
    space = Space(
        tenant_id=tenant_id,
        name=f"Space PDF {suffix}",
        slug=f"space-pdf-{suffix}",
        capacidad_maxima=100,
        precio_por_hora=500,
    )
    db_super.add(space)
    db_super.commit()
    db_super.refresh(space)
    return space


@pytest.mark.integration
class TestPublicPrecotizacionPdf:
    def test_returns_pdf_bytes_without_auth(self, client, monkeypatch, tenant_a, db_super):
        _set_default_tenant(monkeypatch, tenant_a.id)
        space = _make_space(db_super, tenant_a.id, uuid4().hex[:8])
        fake_pdf = b"%PDF-1.4 fake-wizard-precotizacion"

        with patch(
            "app.modules.booking.precotizacion_pdf.generate_cart_precotizacion_pdf_bytes",
            return_value=fake_pdf,
        ) as mocked:
            response = client.post(
                "/api/public/quote-requests/precotizacion.pdf",
                json={
                    "items": [
                        {
                            "space_id": str(space.id),
                            "fecha": "2026-08-15",
                            "hora_inicio": "09:00:00",
                            "hora_fin": "15:00:00",
                        }
                    ],
                    "discount_code": None,
                    "client_name": "Ana Prueba",
                    "client_email": "ana@example.com",
                    "event_name": "Conferencia",
                    "document_ref": "BCE-20260715-172822-2973",
                    "asistentes_estimados": 80,
                },
            )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/pdf")
        assert "precotizacion-" in response.headers.get("content-disposition", "")
        assert response.content == fake_pdf
        mocked.assert_called_once()

    def test_unknown_space_422(self, client, monkeypatch, tenant_a):
        _set_default_tenant(monkeypatch, tenant_a.id)

        response = client.post(
            "/api/public/quote-requests/precotizacion.pdf",
            json={
                "items": [
                    {
                        "space_id": str(uuid4()),
                        "fecha": "2026-08-15",
                        "hora_inicio": "09:00:00",
                        "hora_fin": "10:00:00",
                    }
                ],
                "client_name": "X",
                "client_email": "x@example.com",
            },
        )

        assert response.status_code == 422
        assert response.json()["detail"]["reason"] == "UNKNOWN_SPACE"

    def test_empty_items_422(self, client, monkeypatch, tenant_a):
        _set_default_tenant(monkeypatch, tenant_a.id)

        response = client.post(
            "/api/public/quote-requests/precotizacion.pdf",
            json={"items": []},
        )

        assert response.status_code == 422
