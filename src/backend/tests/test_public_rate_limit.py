"""Integration tests for per-IP rate limiting on public endpoints (PR#10,
REQ-012 — merge-to-main gate, 4R security review).

The three public (no-JWT) endpoints were completely unthrottled: email
bombing on submit, disk-fill via uploads, and DB/Portal amplification via
price-preview (cheapest vector — needs no valid folio). This suite asserts:
  1. Exceeding the configured limit returns 429 for each endpoint.
  2. Under-limit requests still succeed with their normal status code.
  3. The `key_func` buckets by `X-Forwarded-For` (real client IP behind
     nginx), not by the raw TestClient/nginx socket IP.
  4. The limiter fails OPEN when the Redis storage backend errors.

Limits are monkeypatched LOW (2-3/minute) for deterministic assertions —
production defaults (20/30/5 per minute) are far too high to hit in a fast
test. The global `_reset_rate_limit_storage` autouse fixture in
`tests/conftest.py` resets `limiter` storage before/after EVERY test in the
whole suite (not just this file) so counts never leak across tests or
pollute the shared rate-limit Redis DB (see
`Settings.RATE_LIMIT_STORAGE_URI` — a dedicated DB index, distinct from the
Celery broker's).
"""

import app.api.public as public_module
from app.core.config import settings
from app.core.rate_limit import limiter
from app.modules.portal_gate.client import PortalFolioStatus
from tests.conftest import unique_portal_folio


class TestValidateFolioRateLimit:
    def test_exceeding_limit_returns_429(self, client, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMIT_VALIDATE_FOLIO", "2/minute")
        monkeypatch.setattr(
            public_module.portal_gate_client,
            "validate_folio",
            lambda f: PortalFolioStatus.ELIGIBLE,
        )

        headers = {"X-Forwarded-For": "203.0.113.10"}
        payload = {"folio": unique_portal_folio()}

        r1 = client.post("/api/public/quote-requests/validate-folio", json=payload, headers=headers)
        r2 = client.post("/api/public/quote-requests/validate-folio", json=payload, headers=headers)
        r3 = client.post("/api/public/quote-requests/validate-folio", json=payload, headers=headers)

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r3.status_code == 429
        body = r3.json()
        assert body["reason"] == "RATE_LIMIT_EXCEEDED"

    def test_under_limit_requests_still_succeed(self, client, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMIT_VALIDATE_FOLIO", "5/minute")
        monkeypatch.setattr(
            public_module.portal_gate_client,
            "validate_folio",
            lambda f: PortalFolioStatus.ELIGIBLE,
        )
        headers = {"X-Forwarded-For": "203.0.113.11"}

        for _ in range(3):
            response = client.post(
                "/api/public/quote-requests/validate-folio",
                json={"folio": unique_portal_folio()},
                headers=headers,
            )
            assert response.status_code == 200


class TestPricePreviewRateLimit:
    def test_exceeding_limit_returns_429(self, client, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMIT_PRICE_PREVIEW", "2/minute")
        monkeypatch.setattr(settings, "DEFAULT_TENANT_ID", "00000000-0000-0000-0000-000000000001")
        headers = {"X-Forwarded-For": "203.0.113.20"}
        # Empty `items` is a cheap, always-valid-shape payload — the rate
        # limiter runs BEFORE route validation/business logic, so this is
        # enough to exercise throttling without needing real spaces/pricing
        # rules; the endpoint just returns an empty result under the limit.
        payload = {"items": []}

        r1 = client.post("/api/public/quote-requests/price-preview", json=payload, headers=headers)
        r2 = client.post("/api/public/quote-requests/price-preview", json=payload, headers=headers)
        r3 = client.post("/api/public/quote-requests/price-preview", json=payload, headers=headers)

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r3.status_code == 429


class TestSubmitRateLimit:
    def test_exceeding_limit_returns_429(self, client, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMIT_SUBMIT", "2/minute")
        headers = {"X-Forwarded-For": "203.0.113.30"}
        # Deliberately invalid multipart payload — the limiter runs before
        # parsing/validation, so 422s from bad JSON still count against the
        # bucket, which is exactly what we're asserting.
        data = {"payload": "not-json"}

        r1 = client.post("/api/public/quote-requests", data=data, headers=headers)
        r2 = client.post("/api/public/quote-requests", data=data, headers=headers)
        r3 = client.post("/api/public/quote-requests", data=data, headers=headers)

        assert r1.status_code == 422
        assert r2.status_code == 422
        assert r3.status_code == 429


class TestKeyFuncBucketsByForwardedFor:
    def test_different_xff_values_get_independent_buckets(self, client, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMIT_VALIDATE_FOLIO", "1/minute")
        monkeypatch.setattr(
            public_module.portal_gate_client,
            "validate_folio",
            lambda f: PortalFolioStatus.ELIGIBLE,
        )

        headers_a = {"X-Forwarded-For": "198.51.100.1"}
        headers_b = {"X-Forwarded-For": "198.51.100.2"}

        r_a1 = client.post(
            "/api/public/quote-requests/validate-folio",
            json={"folio": unique_portal_folio()},
            headers=headers_a,
        )
        r_b1 = client.post(
            "/api/public/quote-requests/validate-folio",
            json={"folio": unique_portal_folio()},
            headers=headers_b,
        )

        # Both IPs get their own first hit for free — proves the bucket key
        # is the XFF value, not a single shared key (e.g. nginx's IP or a
        # constant), which would have made r_b1 429 immediately.
        assert r_a1.status_code == 200
        assert r_b1.status_code == 200

    def test_same_xff_value_shares_bucket(self, client, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMIT_VALIDATE_FOLIO", "1/minute")
        monkeypatch.setattr(
            public_module.portal_gate_client,
            "validate_folio",
            lambda f: PortalFolioStatus.ELIGIBLE,
        )
        headers = {"X-Forwarded-For": "198.51.100.3"}

        r1 = client.post(
            "/api/public/quote-requests/validate-folio",
            json={"folio": unique_portal_folio()},
            headers=headers,
        )
        r2 = client.post(
            "/api/public/quote-requests/validate-folio",
            json={"folio": unique_portal_folio()},
            headers=headers,
        )

        assert r1.status_code == 200
        assert r2.status_code == 429


class TestGetClientIp:
    """Unit-level check of the key_func precedence (XFF > X-Real-IP >
    request.client.host), independent of the live limiter/Redis."""

    def test_uses_first_hop_of_x_forwarded_for(self):
        from unittest.mock import MagicMock

        from app.core.rate_limit import get_client_ip

        request = MagicMock()
        request.headers = {"x-forwarded-for": "10.0.0.5, 172.18.0.1"}
        request.client = MagicMock(host="172.18.0.1")

        assert get_client_ip(request) == "10.0.0.5"

    def test_falls_back_to_x_real_ip(self):
        from unittest.mock import MagicMock

        from app.core.rate_limit import get_client_ip

        request = MagicMock()
        request.headers = {"x-real-ip": "10.0.0.9"}
        request.client = MagicMock(host="172.18.0.1")

        assert get_client_ip(request) == "10.0.0.9"

    def test_falls_back_to_request_client_host(self):
        from unittest.mock import MagicMock

        from app.core.rate_limit import get_client_ip

        request = MagicMock()
        request.headers = {}
        request.client = MagicMock(host="172.18.0.1")

        assert get_client_ip(request) == "172.18.0.1"


class TestFailOpenOnStorageError:
    def test_storage_error_allows_request_through(self, client, monkeypatch):
        """`swallow_errors=True` (see `app/core/rate_limit.py`) must make a
        broken storage backend fail OPEN — a Redis blip must never take
        down public endpoints."""
        monkeypatch.setattr(settings, "RATE_LIMIT_VALIDATE_FOLIO", "1/minute")
        monkeypatch.setattr(
            public_module.portal_gate_client,
            "validate_folio",
            lambda f: PortalFolioStatus.ELIGIBLE,
        )

        def _broken_incr(*args, **kwargs):
            raise ConnectionError("simulated Redis outage")

        monkeypatch.setattr(limiter._storage, "incr", _broken_incr)

        response = client.post(
            "/api/public/quote-requests/validate-folio",
            json={"folio": unique_portal_folio()},
            headers={"X-Forwarded-For": "203.0.113.99"},
        )

        # Fails OPEN: request still served normally, not 429/500.
        assert response.status_code == 200
