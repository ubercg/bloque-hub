"""Unit tests for the Portal gate HTTP client (REQ-012, design.md §3).

These are pure unit tests: httpx transport is mocked via httpx.MockTransport,
no DB required.
"""

import httpx
import pytest

from app.core.config import settings
from app.modules.portal_gate.client import (
    PortalFolioStatus,
    PortalUnavailableError,
    validate_folio,
)

VALID_FOLIO = "BCE-20260715-172822-2973"
INVALID_FOLIO = "ABC-123"


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
            return httpx.Response(200, json={"status": "quotation_in_progress"})

        _patch_client(monkeypatch, handler)

        result = validate_folio(VALID_FOLIO)

        assert result == PortalFolioStatus.ELIGIBLE

    def test_200_other_status_returns_not_eligible(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": "quotation_sent"})

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
            return httpx.Response(200, json={"status": "quotation_in_progress"})

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
