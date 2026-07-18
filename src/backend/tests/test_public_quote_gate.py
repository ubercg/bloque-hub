"""Integration tests for the public folio gate endpoint (REQ-012, Phase 4 / PR#4).

`POST /api/public/quote-requests/validate-folio` — format check first (RN-017,
no Portal call on malformed folio), then Portal eligibility (RN-001/002/003)
with a distinct PORTAL_UNAVAILABLE taxonomy (resilience requirement).
"""

from uuid import uuid4

import app.api.public as public_module
from app.modules.portal_gate.client import PortalFolioStatus, PortalUnavailableError

VALID_FOLIO = "BCE-20260715-172822-2973"


def _valid_folio() -> str:
    return f"BCE-20260715-172822-{uuid4().int % 10000:04d}"


class TestFolioFormatValidation:
    def test_malformed_folio_returns_422_and_never_calls_portal(self, client, monkeypatch):
        called = {"count": 0}

        def _spy(folio: str):
            called["count"] += 1
            return PortalFolioStatus.ELIGIBLE

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
            return PortalFolioStatus.ELIGIBLE

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
            lambda f: PortalFolioStatus.ELIGIBLE,
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
            lambda f: PortalFolioStatus.NOT_ELIGIBLE,
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
