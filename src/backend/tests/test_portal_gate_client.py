"""Unit tests for the Portal gate HTTP client (REQ-013, design.md §3-4-5).

These are pure unit tests: httpx transport is mocked via httpx.MockTransport,
no DB required. The real REQ-013 contract: `data.status` envelope (nested,
never root `status`), three `X-Bloque-*` HMAC headers signed via
`PortalHmacAuth` on every call, integration route only (no public-route
fallback, RN-002), and (Slice B2) the exhaustive error-code taxonomy that
resolves every documented Portal failure to a `PortalGateResult` — never a
bare enum, so a caller can never forget to check `.status`.
"""

import httpx
import pytest

from app.core.config import settings
from app.modules.portal_gate.client import (
    PORTAL_INTEGRATION_PATH_TEMPLATE,
    PortalFolioStatus,
    PortalGateResult,
    PortalUnavailableError,
    validate_folio,
)
from app.modules.portal_gate.prefill import LeadPrefill
from app.modules.portal_gate.signing import (
    API_KEY_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
)

VALID_FOLIO = "BCE-20260715-172822-2973"
INVALID_FOLIO = "ABC-123"


@pytest.fixture(autouse=True)
def _no_secret_leak_in_any_log(caplog):
    """Structural invariant (design §4.1): the secret, the literal
    `X-Bloque-Signature`, and the canonical string must appear in NO emitted
    record — checked after EVERY test in this module, not just the ones that
    exercise a failure path, so a future change cannot quietly reintroduce a
    leak through a code path this file doesn't explicitly test.
    """
    caplog.set_level("DEBUG", logger="app.modules.portal_gate.client")
    yield
    secret = settings.PORTAL_HUB_API_SECRET
    for record in caplog.records:
        message = record.getMessage()
        assert secret not in message, f"secret leaked in log record: {message!r}"
        assert "X-Bloque-Signature" not in message
        assert "GET\n" not in message  # canonical string's method+separator


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


class TestPortalGateResultConstructors:
    """Pure, no HTTP (task 4.1) — the classmethods are the entire public
    surface a fake needs to know about to stay in sync with the real type."""

    def test_eligible_defaults_prefill_and_error_code_to_none(self):
        result = PortalGateResult.eligible()

        assert result.status == PortalFolioStatus.ELIGIBLE
        assert result.prefill is None
        assert result.error_code is None

    def test_eligible_accepts_a_placeholder_prefill(self):
        placeholder = {"nombre_completo": "Ana Lopez"}

        result = PortalGateResult.eligible(prefill=placeholder)

        assert result.prefill == placeholder

    def test_of_builds_a_non_eligible_result_with_no_prefill(self):
        result = PortalGateResult.of(PortalFolioStatus.NOT_ELIGIBLE)

        assert result.status == PortalFolioStatus.NOT_ELIGIBLE
        assert result.prefill is None
        assert result.error_code is None

    def test_of_carries_an_error_code(self):
        result = PortalGateResult.of(
            PortalFolioStatus.INTEGRATION_AUTH_FAILURE, error_code="INVALID_SIGNATURE"
        )

        assert result.status == PortalFolioStatus.INTEGRATION_AUTH_FAILURE
        assert result.error_code == "INVALID_SIGNATURE"


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

        assert result.status == PortalFolioStatus.NOT_ELIGIBLE
        assert called["count"] == 0


class TestValidateFolioPortalResponses:
    def test_200_quotation_in_progress_returns_eligible(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            assert VALID_FOLIO in str(request.url)
            return httpx.Response(200, json=_eligible_envelope())

        _patch_client(monkeypatch, handler)

        result = validate_folio(VALID_FOLIO)

        assert result.status == PortalFolioStatus.ELIGIBLE

    def test_200_other_status_returns_not_eligible(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": {"status": "quotation_sent"}})

        _patch_client(monkeypatch, handler)

        result = validate_folio(VALID_FOLIO)

        assert result.status == PortalFolioStatus.NOT_ELIGIBLE

    def test_404_returns_not_eligible_without_retry(self, monkeypatch):
        called = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            called["count"] += 1
            return httpx.Response(404, json={"detail": "not found"})

        _patch_client(monkeypatch, handler)

        result = validate_folio(VALID_FOLIO)

        assert result.status == PortalFolioStatus.NOT_ELIGIBLE
        assert called["count"] == 1

    def test_403_returns_not_eligible_without_retry(self, monkeypatch):
        called = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            called["count"] += 1
            return httpx.Response(403, json={"detail": "forbidden"})

        _patch_client(monkeypatch, handler)

        result = validate_folio(VALID_FOLIO)

        assert result.status == PortalFolioStatus.NOT_ELIGIBLE
        assert called["count"] == 1


class TestValidateFolioPrefillWiring:
    """Slice C wiring (design §6, §11): `_resolve_success` calls
    `map_lead_prefill` on the REAL envelope shape — `data.lead_prefill`,
    fixed in `portal-mock.py` (Slice E) — never a top-level `lead_prefill`
    key."""

    def test_eligible_with_lead_prefill_maps_into_result(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "status": "quotation_in_progress",
                        "lead_prefill": {
                            "nombre_completo": "Ana Torres",
                            "requestor_name": "Ana Torres",
                            "correo_institucional": "ana.torres@example.com",
                            "contact_email": "ana.torres@example.com",
                            "telefono_contacto": "5512345678",
                            "contact_phone": "5512345678",
                            "asistentes_estimados": 150,
                            "attendees": 150,
                            "fecha_tentativa": "2026-08-20",
                            "date": "2026-08-20",
                            "tipo_evento_sugerido": "boda",
                            "event_type": "boda",
                            "espacio_requerido": "Salon Jacarandas",
                            "comentarios": "Sonido especial.",
                            "special_notes": "Sonido especial.",
                            "como_conociste_bloque": "redes_sociales",
                            "how_learned_bloque": "redes_sociales",
                            "ciudad": "Queretaro",
                            "space_id": "trap-uuid",
                        },
                    }
                },
            )

        _patch_client(monkeypatch, handler)

        result = validate_folio(VALID_FOLIO)

        assert result.status == PortalFolioStatus.ELIGIBLE
        assert isinstance(result.prefill, LeadPrefill)
        assert result.prefill.nombre_completo == "Ana Torres"
        assert result.prefill.correo_institucional == "ana.torres@example.com"
        assert result.prefill.requerimientos_especiales == "Sonido especial."
        assert not hasattr(result.prefill, "ciudad")

    def test_eligible_without_lead_prefill_key_returns_all_none_prefill(self, monkeypatch):
        _patch_client(
            monkeypatch,
            lambda request: httpx.Response(200, json=_eligible_envelope()),
        )

        result = validate_folio(VALID_FOLIO)

        assert result.status == PortalFolioStatus.ELIGIBLE
        assert result.prefill == LeadPrefill(*([None] * 11))

    def test_not_eligible_result_never_carries_a_prefill(self, monkeypatch):
        _patch_client(
            monkeypatch,
            lambda request: httpx.Response(200, json={"data": {"status": "quotation_sent"}}),
        )

        result = validate_folio(VALID_FOLIO)

        assert result.status == PortalFolioStatus.NOT_ELIGIBLE
        assert result.prefill is None


class TestValidateFolioAuthFailureTaxonomy:
    """REQ-013 §4.5 / design §4: every deterministic 401 `error_code`
    resolves to `INTEGRATION_AUTH_FAILURE` with exactly ONE HTTP request —
    none of these are retried, unlike the 429/5xx transport bucket."""

    @pytest.mark.parametrize(
        "error_code",
        ["MISSING_CREDENTIALS", "UNKNOWN_API_KEY", "INVALID_SIGNATURE", "MALFORMED_TIMESTAMP"],
    )
    def test_deterministic_401_resolves_to_auth_failure_with_one_request(
        self, monkeypatch, error_code
    ):
        called = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            called["count"] += 1
            return httpx.Response(401, json={"error_code": error_code})

        _patch_client(monkeypatch, handler, sleep_calls=[])

        result = validate_folio(VALID_FOLIO)

        assert result.status == PortalFolioStatus.INTEGRATION_AUTH_FAILURE
        assert result.error_code == error_code
        assert called["count"] == 1

    def test_401_without_error_code_still_resolves_to_auth_failure(self, monkeypatch):
        # Malformed/absent error_code body — must fail loudly to a mapped
        # status, never crash and never quietly become NOT_ELIGIBLE.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"detail": "unauthorized"})

        _patch_client(monkeypatch, handler, sleep_calls=[])

        result = validate_folio(VALID_FOLIO)

        assert result.status == PortalFolioStatus.INTEGRATION_AUTH_FAILURE
        assert result.error_code is None

    def test_timestamp_expired_refire_costs_exactly_two_requests(self, monkeypatch):
        # The re-fire happens INSIDE auth.py's auth_flow, inside ONE
        # `client.get(...)` call — it must never touch the client.py
        # transport-retry loop (no sleep, no second `attempt`).
        sleep_calls = []
        calls = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            return httpx.Response(401, json={"error_code": "TIMESTAMP_EXPIRED"})

        _patch_client(monkeypatch, handler, sleep_calls=sleep_calls)

        result = validate_folio(VALID_FOLIO)

        assert result.status == PortalFolioStatus.INTEGRATION_AUTH_FAILURE
        assert calls["count"] == 2
        assert sleep_calls == []

    def test_timestamp_expired_then_deterministic_401_is_still_two_requests(
        self, monkeypatch
    ):
        sleep_calls = []
        calls = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            if calls["count"] == 1:
                return httpx.Response(401, json={"error_code": "TIMESTAMP_EXPIRED"})
            return httpx.Response(401, json={"error_code": "INVALID_SIGNATURE"})

        _patch_client(monkeypatch, handler, sleep_calls=sleep_calls)

        result = validate_folio(VALID_FOLIO)

        assert result.status == PortalFolioStatus.INTEGRATION_AUTH_FAILURE
        assert result.error_code == "INVALID_SIGNATURE"
        assert calls["count"] == 2
        assert sleep_calls == []


class TestValidateFolioNotEligibleTaxonomy:
    """REQ-013 §4.5: 403 NOT_ELIGIBLE/TERMINAL and 404 FOLIO_NOT_FOUND all
    collapse to the same `NOT_ELIGIBLE` result, with no retry."""

    @pytest.mark.parametrize(
        "status_code,error_code",
        [(403, "NOT_ELIGIBLE"), (403, "TERMINAL"), (404, "FOLIO_NOT_FOUND")],
    )
    def test_variant_resolves_to_not_eligible_with_one_request(
        self, monkeypatch, status_code, error_code
    ):
        called = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            called["count"] += 1
            return httpx.Response(status_code, json={"error_code": error_code})

        _patch_client(monkeypatch, handler, sleep_calls=[])

        result = validate_folio(VALID_FOLIO)

        assert result.status == PortalFolioStatus.NOT_ELIGIBLE
        assert called["count"] == 1


class TestValidateFolioRetryableTaxonomy:
    """429/5xx/timeout map to UNAVAILABLE via the transport retry loop
    (expressed as `PortalUnavailableError`, matching the pre-existing
    behavior — the loop's job is to retry, not to hand back a bare status)."""

    def test_429_exhausts_retries_then_raises_with_expected_request_count(
        self, monkeypatch
    ):
        sleep_calls = []
        called = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            called["count"] += 1
            return httpx.Response(429, json={"detail": "too many requests"})

        _patch_client(monkeypatch, handler, sleep_calls=sleep_calls)

        with pytest.raises(PortalUnavailableError):
            validate_folio(VALID_FOLIO)

        assert called["count"] == settings.PORTAL_RETRY_ATTEMPTS


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


class TestAuthFailureLogging:
    """REQ-013 §4.1 `portal_gate.auth_failure` marker — masked folio,
    error_code, the PUBLIC api_key (explicitly permitted by RN-018), host,
    and latency_ms. Never the full folio, never the secret, never the
    signature (checked module-wide by the autouse fixture above)."""

    def test_auth_failure_marker_carries_the_documented_fields(
        self, monkeypatch, caplog
    ):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error_code": "INVALID_SIGNATURE"})

        _patch_client(monkeypatch, handler, sleep_calls=[])

        with caplog.at_level("ERROR", logger="app.modules.portal_gate.client"):
            result = validate_folio(VALID_FOLIO)

        assert result.status == PortalFolioStatus.INTEGRATION_AUTH_FAILURE
        records = [r for r in caplog.records if "portal_gate.auth_failure" in r.getMessage()]
        assert len(records) == 1
        message = records[0].getMessage()
        assert "error_code=INVALID_SIGNATURE" in message
        assert f"api_key={settings.PORTAL_HUB_API_KEY}" in message
        assert "latency_ms=" in message
        assert VALID_FOLIO not in message

    def test_auth_failure_marker_uses_unknown_when_error_code_is_absent(
        self, monkeypatch, caplog
    ):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"detail": "unauthorized"})

        _patch_client(monkeypatch, handler, sleep_calls=[])

        with caplog.at_level("ERROR", logger="app.modules.portal_gate.client"):
            validate_folio(VALID_FOLIO)

        records = [r for r in caplog.records if "portal_gate.auth_failure" in r.getMessage()]
        assert len(records) == 1
        assert "error_code=UNKNOWN" in records[0].getMessage()


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

        assert result.status == PortalFolioStatus.ELIGIBLE
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

    def test_integration_route_is_called_even_on_a_401(self, monkeypatch):
        # Regression guard for RN-002: an auth failure must never trigger a
        # fallback request to the retired public route.
        seen_urls = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_urls.append(str(request.url))
            return httpx.Response(401, json={"error_code": "INVALID_SIGNATURE"})

        _patch_client(monkeypatch, handler, sleep_calls=[])

        validate_folio(VALID_FOLIO)

        assert len(seen_urls) == 1
        assert "space-event-requests" not in seen_urls[0]


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
        assert "latency_ms=" in message
