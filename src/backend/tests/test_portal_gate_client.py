"""Unit tests for the Portal gate HTTP client (REQ-013, design.md §3-4).

These are pure unit tests: httpx transport is mocked via httpx.MockTransport,
no DB required. The real REQ-013 contract: `data.status` envelope (nested,
never root `status`), three `X-Bloque-*` HMAC headers signed via
`PortalHmacAuth` on every call, integration route only (no public-route
fallback, RN-002).
"""

import httpx
import pytest

from app.core.config import settings
from app.modules.portal_gate.client import (
    PORTAL_INTEGRATION_PATH_TEMPLATE,
    PortalFolioStatus,
    PortalUnavailableError,
    validate_folio,
)
from app.modules.portal_gate.signing import (
    API_KEY_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
)

VALID_FOLIO = "BCE-20260715-172822-2973"
INVALID_FOLIO = "ABC-123"


def _eligible_envelope() -> dict:
    return {"data": {"status": "quotation_in_progress"}}


def _patch_client(monkeypatch, handler, sleep_calls=None):
    """Patch httpx.Client construction inside the portal_gate client module
    so requests go through a MockTransport-backed client instead of the network.
    """
    transport = httpx.MockTransport(handler)

    import app.modules.portal_gate.client as client_module

    original_client_cls = httpx.Client

    def _client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client_cls(*args, **kwargs)

    monkeypatch.setattr(client_module.httpx, "Client", _client_factory)

    if sleep_calls is not None:
        monkeypatch.setattr(
            client_module.time,
            "sleep",
            lambda seconds: sleep_calls.append(seconds),
        )


class TestValidateFolioFormat:
    def test_invalid_format_returns_not_eligible_without_calling_portal(
        self, monkeypatch
    ):
        called = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            called["count"] += 1
            return httpx.Response(200, json={"status": "quotation_in_progress"})

        _patch_client(monkeypatch, handler)

        result = validate_folio(INVALID_FOLIO)

        assert result == PortalFolioStatus.NOT_ELIGIBLE
        assert called["count"] == 0


class TestValidateFolioPortalResponses:
    def test_200_quotation_in_progress_returns_eligible(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            assert VALID_FOLIO in str(request.url)
            return httpx.Response(200, json=_eligible_envelope())

        _patch_client(monkeypatch, handler)

        result = validate_folio(VALID_FOLIO)

        assert result == PortalFolioStatus.ELIGIBLE

    def test_200_other_status_returns_not_eligible(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": {"status": "quotation_sent"}})

        _patch_client(monkeypatch, handler)

        result = validate_folio(VALID_FOLIO)

        assert result == PortalFolioStatus.NOT_ELIGIBLE

    def test_404_returns_not_eligible_without_retry(self, monkeypatch):
        called = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            called["count"] += 1
            return httpx.Response(404, json={"detail": "not found"})

        _patch_client(monkeypatch, handler)

        result = validate_folio(VALID_FOLIO)

        assert result == PortalFolioStatus.NOT_ELIGIBLE
        assert called["count"] == 1

    def test_403_returns_not_eligible_without_retry(self, monkeypatch):
        called = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            called["count"] += 1
            return httpx.Response(403, json={"detail": "forbidden"})

        _patch_client(monkeypatch, handler)

        result = validate_folio(VALID_FOLIO)

        assert result == PortalFolioStatus.NOT_ELIGIBLE
        assert called["count"] == 1


class TestValidateFolioUnexpectedStatus:
    """PR#9 FIX 5 (CRITICAL): an UNEXPECTED status code (not 200/403/404/5xx)
    — e.g. a rotated API key returning 401, or rate-limiting returning 429 —
    must NOT silently masquerade as a business rejection (NOT_ELIGIBLE). It
    must be treated as Portal-unavailable/misconfigured, not swallowed."""

    def test_401_does_not_return_not_eligible(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"detail": "unauthorized"})

        _patch_client(monkeypatch, handler, sleep_calls=[])

        with pytest.raises(PortalUnavailableError):
            validate_folio(VALID_FOLIO)

    def test_429_does_not_return_not_eligible(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"detail": "too many requests"})

        _patch_client(monkeypatch, handler, sleep_calls=[])

        with pytest.raises(PortalUnavailableError):
            validate_folio(VALID_FOLIO)


class TestValidateFolioLogging:
    """PR#9 FIX 5 (CRITICAL): portal_gate had zero logging — retries and
    final failures were invisible in production. Assert a WARNING is emitted
    on each retryable failure and on the final PortalUnavailableError."""

    def test_5xx_retry_logs_warning_with_attempt_and_folio(self, monkeypatch, caplog):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"detail": "service unavailable"})

        _patch_client(monkeypatch, handler, sleep_calls=[])

        with caplog.at_level("WARNING", logger="app.modules.portal_gate.client"):
            with pytest.raises(PortalUnavailableError):
                validate_folio(VALID_FOLIO)

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) >= settings.PORTAL_RETRY_ATTEMPTS
        assert any(VALID_FOLIO in r.getMessage() for r in warnings)

    def test_unexpected_status_logs_warning(self, monkeypatch, caplog):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"detail": "unauthorized"})

        _patch_client(monkeypatch, handler, sleep_calls=[])

        with caplog.at_level("WARNING", logger="app.modules.portal_gate.client"):
            with pytest.raises(PortalUnavailableError):
                validate_folio(VALID_FOLIO)

        assert any(r.levelname == "WARNING" for r in caplog.records)


class TestValidateFolioRetryBehavior:
    def test_timeout_then_success_returns_eligible_and_retries(self, monkeypatch):
        sleep_calls = []
        called = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            called["count"] += 1
            if called["count"] == 1:
                raise httpx.TimeoutException("timed out", request=request)
            return httpx.Response(200, json=_eligible_envelope())

        _patch_client(monkeypatch, handler, sleep_calls=sleep_calls)

        result = validate_folio(VALID_FOLIO)

        assert result == PortalFolioStatus.ELIGIBLE
        assert called["count"] == 2
        assert len(sleep_calls) == 1

    def test_timeout_exhausted_raises_portal_unavailable(self, monkeypatch):
        sleep_calls = []
        called = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            called["count"] += 1
            raise httpx.TimeoutException("timed out", request=request)

        _patch_client(monkeypatch, handler, sleep_calls=sleep_calls)

        with pytest.raises(PortalUnavailableError):
            validate_folio(VALID_FOLIO)

        assert called["count"] == settings.PORTAL_RETRY_ATTEMPTS

    def test_5xx_exhausted_raises_portal_unavailable(self, monkeypatch):
        sleep_calls = []
        called = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            called["count"] += 1
            return httpx.Response(503, json={"detail": "service unavailable"})

        _patch_client(monkeypatch, handler, sleep_calls=sleep_calls)

        with pytest.raises(PortalUnavailableError):
            validate_folio(VALID_FOLIO)

        assert called["count"] == settings.PORTAL_RETRY_ATTEMPTS


class TestPortalRetryConfigClamping:
    """PR#9 FIX 7 (SUGGESTION): a misconfigured PORTAL_RETRY_ATTEMPTS (e.g. 0
    or 500) must not disable retries entirely or block a request for minutes.
    Attempts are clamped to [1, 5] and backoff is capped."""

    def test_attempts_above_max_are_clamped(self, monkeypatch):
        from app.modules.portal_gate import client as client_module

        monkeypatch.setattr(settings, "PORTAL_RETRY_ATTEMPTS", 500)
        assert client_module._resolved_retry_attempts() <= 5

    def test_attempts_below_min_are_clamped(self, monkeypatch):
        from app.modules.portal_gate import client as client_module

        monkeypatch.setattr(settings, "PORTAL_RETRY_ATTEMPTS", 0)
        assert client_module._resolved_retry_attempts() >= 1

    def test_backoff_is_capped_across_many_attempts(self, monkeypatch):
        from app.modules.portal_gate import client as client_module

        sleep_calls = []
        called = {"count": 0}
        monkeypatch.setattr(settings, "PORTAL_RETRY_ATTEMPTS", 500)

        def handler(request: httpx.Request) -> httpx.Response:
            called["count"] += 1
            return httpx.Response(503, json={"detail": "service unavailable"})

        _patch_client(monkeypatch, handler, sleep_calls=sleep_calls)

        with pytest.raises(PortalUnavailableError):
            validate_folio(VALID_FOLIO)

        assert sleep_calls, "expected at least one retry backoff"
        assert all(delay <= 2.0 for delay in sleep_calls)


class TestValidateFolioIntegrationRoute:
    """REQ-013 §10 row 1 / RN-002: the integration route is the ONLY route.
    No fallback to the retired public route on any status, including 401."""

    def test_integration_route_is_called(self, monkeypatch):
        seen_urls = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_urls.append(str(request.url))
            return httpx.Response(200, json=_eligible_envelope())

        _patch_client(monkeypatch, handler)

        validate_folio(VALID_FOLIO)

        expected_path = PORTAL_INTEGRATION_PATH_TEMPLATE.format(folio=VALID_FOLIO)
        assert seen_urls == [f"{settings.PORTAL_API_BASE_URL.rstrip('/')}{expected_path}"]
        assert "space-event-requests" not in seen_urls[0]

    def test_integration_route_used_for_a_different_folio(self, monkeypatch):
        other_folio = "BCE-20260101-000000-0001"
        seen_urls = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_urls.append(str(request.url))
            return httpx.Response(200, json=_eligible_envelope())

        _patch_client(monkeypatch, handler)

        validate_folio(other_folio)

        expected_path = PORTAL_INTEGRATION_PATH_TEMPLATE.format(folio=other_folio)
        assert seen_urls == [f"{settings.PORTAL_API_BASE_URL.rstrip('/')}{expected_path}"]


class TestValidateFolioSignedHeaders:
    """REQ-013 §4.2/§4.3: every outbound call is signed — no more X-Api-Key."""

    def test_three_headers_present_on_every_request(self, monkeypatch):
        seen_headers = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_headers.append(dict(request.headers))
            return httpx.Response(200, json=_eligible_envelope())

        _patch_client(monkeypatch, handler)

        validate_folio(VALID_FOLIO)

        assert len(seen_headers) == 1
        headers = {k.lower(): v for k, v in seen_headers[0].items()}
        assert headers.get(API_KEY_HEADER.lower())
        assert headers.get(TIMESTAMP_HEADER.lower())
        assert headers.get(SIGNATURE_HEADER.lower())
        assert "x-api-key" not in headers

    def test_headers_present_on_a_retried_request_too(self, monkeypatch):
        seen_headers = []
        called = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            called["count"] += 1
            seen_headers.append(dict(request.headers))
            if called["count"] == 1:
                return httpx.Response(503, json={"detail": "service unavailable"})
            return httpx.Response(200, json=_eligible_envelope())

        _patch_client(monkeypatch, handler, sleep_calls=[])

        validate_folio(VALID_FOLIO)

        assert len(seen_headers) == 2
        for headers in seen_headers:
            headers = {k.lower(): v for k, v in headers.items()}
            assert headers.get(API_KEY_HEADER.lower())
            assert headers.get(TIMESTAMP_HEADER.lower())
            assert headers.get(SIGNATURE_HEADER.lower())


class TestValidateFolioContractViolation:
    """RN-009: a 200 with no `data.status` is a contract violation, NEVER a
    business rejection. It must surface as PortalUnavailableError (503 at the
    API layer), not as NOT_ELIGIBLE and not as a bare UNAVAILABLE return that
    a caller could mistake for a normal enum value."""

    def test_missing_data_status_is_contract_violation(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": {"status_label": "weird"}})

        _patch_client(monkeypatch, handler)

        with pytest.raises(PortalUnavailableError):
            validate_folio(VALID_FOLIO)

    def test_missing_data_key_entirely_is_contract_violation(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": "shape"})

        _patch_client(monkeypatch, handler)

        with pytest.raises(PortalUnavailableError):
            validate_folio(VALID_FOLIO)

    def test_missing_data_status_logs_contract_violation_with_keys_only(
        self, monkeypatch, caplog
    ):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "data": {"nombre_completo": "Applicant Name", "status_label": "weird"},
                    "meta": "ignored",
                },
            )

        _patch_client(monkeypatch, handler)

        with caplog.at_level("ERROR", logger="app.modules.portal_gate.client"):
            with pytest.raises(PortalUnavailableError):
                validate_folio(VALID_FOLIO)

        records = [r for r in caplog.records if "contract_violation" in r.getMessage()]
        assert len(records) == 1
        message = records[0].getMessage()
        assert "Applicant Name" not in message
        assert "data" in message
        assert "meta" in message
