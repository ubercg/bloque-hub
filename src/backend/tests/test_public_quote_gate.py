"""Integration tests for the public folio gate endpoint (REQ-012, Phase 4 / PR#4).

`POST /api/public/quote-requests/validate-folio` — format check first (RN-017,
no Portal call on malformed folio), then Portal eligibility (RN-001/002/003)
with a distinct PORTAL_UNAVAILABLE taxonomy (resilience requirement).
"""

import app.api.public as public_module
from app.modules.portal_gate.client import PortalFolioStatus, PortalGateResult, PortalUnavailableError
from app.modules.portal_gate.prefill import LeadPrefill
from tests.conftest import unique_portal_folio

VALID_FOLIO = "BCE-20260715-172822-2973"


def _valid_folio() -> str:
    return unique_portal_folio()


class TestFolioFormatValidation:
    def test_malformed_folio_returns_422_and_never_calls_portal(self, client, monkeypatch):
        called = {"count": 0}

        def _spy(folio: str):
            called["count"] += 1
            return PortalGateResult.eligible()

        monkeypatch.setattr(public_module.portal_gate_client, "validate_folio", _spy)

        response = client.post(
            "/api/public/quote-requests/validate-folio",
            json={"folio": "ABC-123"},
        )

        assert response.status_code == 422
        assert called["count"] == 0

    def test_empty_folio_returns_422_without_calling_portal(self, client, monkeypatch):
        called = {"count": 0}

        def _spy(folio: str):
            called["count"] += 1
            return PortalGateResult.eligible()

        monkeypatch.setattr(public_module.portal_gate_client, "validate_folio", _spy)

        response = client.post(
            "/api/public/quote-requests/validate-folio",
            json={"folio": ""},
        )

        assert response.status_code == 422
        assert called["count"] == 0


class TestFolioGateEligibility:
    def test_eligible_folio_returns_200_unlocked_no_auth_header(self, client, monkeypatch):
        folio = _valid_folio()

        monkeypatch.setattr(
            public_module.portal_gate_client,
            "validate_folio",
            lambda f: PortalGateResult.eligible(),
        )

        response = client.post(
            "/api/public/quote-requests/validate-folio",
            json={"folio": folio},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["unlocked"] is True
        assert body["folio"] == folio

    def test_not_eligible_folio_returns_403_with_rn003_message(self, client, monkeypatch):
        monkeypatch.setattr(
            public_module.portal_gate_client,
            "validate_folio",
            lambda f: PortalGateResult.of(PortalFolioStatus.NOT_ELIGIBLE),
        )

        response = client.post(
            "/api/public/quote-requests/validate-folio",
            json={"folio": _valid_folio()},
        )

        assert response.status_code == 403
        body = response.json()
        assert body["detail"]["reason"] == "FOLIO_NOT_ELIGIBLE"
        assert "no se encuentra disponible" in body["detail"]["message"]

    def test_portal_unavailable_returns_503_distinct_from_403(self, client, monkeypatch):
        def _raise(folio: str):
            raise PortalUnavailableError("Portal unreachable after 3 attempts")

        monkeypatch.setattr(public_module.portal_gate_client, "validate_folio", _raise)

        response = client.post(
            "/api/public/quote-requests/validate-folio",
            json={"folio": _valid_folio()},
        )

        assert response.status_code == 503
        body = response.json()
        assert body["detail"]["reason"] == "PORTAL_UNAVAILABLE"


class TestFolioGateLeadPrefill:
    """Slice C (design §6, §11): `lead_prefill` is populated ONLY on the
    ELIGIBLE success path for the folio just queried — never on an error
    detail body (RN-013/§6, task 5.11)."""

    _FULL_PREFILL = LeadPrefill(
        nombre_completo="Ana Torres",
        cargo_puesto="Directora",
        institucion_organizacion="Municipio Y",
        correo_institucional="ana.torres@example.com",
        telefono_contacto="5512345678",
        asistentes_estimados=150,
        fecha_tentativa="2026-08-20",
        tipo_evento_sugerido="boda",
        espacio_requerido="Salon Jacarandas",
        requerimientos_especiales="Sonido especial.",
        como_conociste_bloque="redes_sociales",
    )

    def test_eligible_with_prefill_populates_every_field(self, client, monkeypatch):
        monkeypatch.setattr(
            public_module.portal_gate_client,
            "validate_folio",
            lambda f: PortalGateResult.eligible(prefill=self._FULL_PREFILL),
        )

        response = client.post(
            "/api/public/quote-requests/validate-folio",
            json={"folio": _valid_folio()},
        )

        assert response.status_code == 200
        lead_prefill = response.json()["lead_prefill"]
        assert lead_prefill["nombre_completo"] == "Ana Torres"
        assert lead_prefill["correo_institucional"] == "ana.torres@example.com"
        assert lead_prefill["requerimientos_especiales"] == "Sonido especial."
        assert lead_prefill["asistentes_estimados"] == 150
        assert "ciudad" not in lead_prefill
        assert "comentarios" not in lead_prefill

    def test_eligible_without_prefill_data_returns_null_lead_prefill(self, client, monkeypatch):
        monkeypatch.setattr(
            public_module.portal_gate_client,
            "validate_folio",
            lambda f: PortalGateResult.eligible(),
        )

        response = client.post(
            "/api/public/quote-requests/validate-folio",
            json={"folio": _valid_folio()},
        )

        assert response.status_code == 200
        assert response.json()["lead_prefill"] is None

    def test_invalid_format_never_returns_lead_prefill(self, client, monkeypatch):
        called = {"count": 0}

        def _spy(folio: str):
            called["count"] += 1
            return PortalGateResult.eligible(prefill=self._FULL_PREFILL)

        monkeypatch.setattr(public_module.portal_gate_client, "validate_folio", _spy)

        response = client.post(
            "/api/public/quote-requests/validate-folio",
            json={"folio": "ABC-123"},
        )

        assert response.status_code == 422
        assert "lead_prefill" not in response.json()
        assert "lead_prefill" not in response.json().get("detail", {})

    def test_not_eligible_never_returns_lead_prefill(self, client, monkeypatch):
        monkeypatch.setattr(
            public_module.portal_gate_client,
            "validate_folio",
            lambda f: PortalGateResult.of(PortalFolioStatus.NOT_ELIGIBLE),
        )

        response = client.post(
            "/api/public/quote-requests/validate-folio",
            json={"folio": _valid_folio()},
        )

        assert response.status_code == 403
        assert "lead_prefill" not in response.json()
        assert "lead_prefill" not in response.json()["detail"]

    def test_portal_unavailable_never_returns_lead_prefill(self, client, monkeypatch):
        def _raise(folio: str):
            raise PortalUnavailableError("Portal unreachable after 3 attempts")

        monkeypatch.setattr(public_module.portal_gate_client, "validate_folio", _raise)

        response = client.post(
            "/api/public/quote-requests/validate-folio",
            json={"folio": _valid_folio()},
        )

        assert response.status_code == 503
        assert "lead_prefill" not in response.json()

    def test_auth_failure_never_returns_lead_prefill(self, client, monkeypatch):
        from app.api.portal_gate_http import PORTAL_AUTH_FAILURE_HTTP_STATUS

        monkeypatch.setattr(
            public_module.portal_gate_client,
            "validate_folio",
            lambda f: PortalGateResult.of(PortalFolioStatus.INTEGRATION_AUTH_FAILURE),
        )

        response = client.post(
            "/api/public/quote-requests/validate-folio",
            json={"folio": _valid_folio()},
        )

        assert response.status_code == PORTAL_AUTH_FAILURE_HTTP_STATUS
        assert "lead_prefill" not in response.json()


class TestFolioGateAuthFailure:
    """REQ-013 §13.1 / task 4.12: any upstream 401 (any error_code) resolves
    to INTEGRATION_AUTH_FAILURE, which the gate endpoint reports as the
    configured status (502 by default, see portal_gate_http.py) — never the
    old `!= ELIGIBLE` catch-all's 403."""

    def test_auth_failure_returns_configured_status_with_reason(self, client, monkeypatch):
        from app.api.portal_gate_http import PORTAL_AUTH_FAILURE_HTTP_STATUS

        monkeypatch.setattr(
            public_module.portal_gate_client,
            "validate_folio",
            lambda f: PortalGateResult.of(
                PortalFolioStatus.INTEGRATION_AUTH_FAILURE, error_code="INVALID_SIGNATURE"
            ),
        )

        response = client.post(
            "/api/public/quote-requests/validate-folio",
            json={"folio": _valid_folio()},
        )

        assert response.status_code == PORTAL_AUTH_FAILURE_HTTP_STATUS
        body = response.json()
        assert body["detail"]["reason"] == "INTEGRATION_AUTH_FAILURE"
        assert response.status_code != 403

    def test_auth_failure_message_has_no_call_to_action(self, client, monkeypatch):
        monkeypatch.setattr(
            public_module.portal_gate_client,
            "validate_folio",
            lambda f: PortalGateResult.of(PortalFolioStatus.INTEGRATION_AUTH_FAILURE),
        )

        response = client.post(
            "/api/public/quote-requests/validate-folio",
            json={"folio": _valid_folio()},
        )

        message = response.json()["detail"]["message"].lower()
        assert "intenta de nuevo" not in message
        assert "contacta" not in message
