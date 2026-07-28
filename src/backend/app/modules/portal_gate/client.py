"""Outbound HTTP client for the BLOQUE Portal folio-access gate (REQ-013).

Design reference: openspec/changes/req-013-portal-hmac/design.md §3, §4.

This is the ONLY outbound HTTP client in the codebase — kept as a small,
isolated adapter. Every request is signed via `PortalHmacAuth` (REQ-013 §4.2)
against the real integration route; there is no fallback route and no
unsigned call.
"""

import enum
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlsplit

import httpx

from app.core.config import settings
from app.modules.portal_gate.auth import PortalHmacAuth

logger = logging.getLogger(__name__)

# REQ-013 §4.2 — the only route. RN-002 forbids falling back to the retired
# public route on any status (including 401); there is nowhere to fall back to.
PORTAL_INTEGRATION_PATH_TEMPLATE = "/api/integrations/bloque-hub/leads/{folio}/access"

# REQ-013 §4.4 — value of the NESTED `data.status` key (never a root-level
# `status` field — that was the old, unconfirmed assumption this replaces).
PORTAL_ELIGIBLE_STATUS_VALUE = "quotation_in_progress"

# RN-017: folio format BCE-YYYYMMDD-HHMMSS-RRRR
FOLIO_PATTERN = re.compile(r"^BCE-\d{8}-\d{6}-\d{4}$")

_RETRYABLE_STATUS_THRESHOLD = 500

# PR#9 FIX 7: clamp a misconfigured PORTAL_RETRY_ATTEMPTS into a sane range —
# 0 (or negative) would disable retries silently, and a very large value
# could block a request for minutes. Backoff itself is also capped below.
_MIN_RETRY_ATTEMPTS = 1
_MAX_RETRY_ATTEMPTS = 5
_MAX_BACKOFF_SECONDS = 2.0


def _resolved_retry_attempts() -> int:
    return max(_MIN_RETRY_ATTEMPTS, min(settings.PORTAL_RETRY_ATTEMPTS, _MAX_RETRY_ATTEMPTS))


def _backoff_seconds(attempt: int) -> float:
    return min(0.2 * 2**attempt, _MAX_BACKOFF_SECONDS)


class PortalFolioStatus(str, enum.Enum):
    ELIGIBLE = "eligible"
    NOT_ELIGIBLE = "not_eligible"
    UNAVAILABLE = "unavailable"
    # REQ-013 §4.5 / design §4, §13.1 — ANY 401, of any error_code, is
    # terminal for the transport loop. This member and the mapping that
    # handles it (`api/portal_gate_http.py`) must merge in the SAME commit
    # as both `public.py` call-site switches — see design §13.1. Adding it
    # here alone, without the mapping, recreates the exact RN-011 violation
    # this change exists to prevent (a `403 FOLIO_NOT_ELIGIBLE` lie for an
    # auth failure, via the old `!= ELIGIBLE` catch-all).
    INTEGRATION_AUTH_FAILURE = "integration_auth_failure"


class PortalGateError(Exception):
    """Base error for the Portal gate client."""


class PortalUnavailableError(PortalGateError):
    """Raised when the Portal API is unreachable after retries are exhausted,
    or when a 200 response violates the REQ-013 §4.4 contract (missing
    `data.status` — RN-009: a contract violation is never a business
    rejection, so it must never resolve to NOT_ELIGIBLE)."""


@dataclass(frozen=True, slots=True)
class PortalGateResult:
    """Result of `validate_folio` (design.md §2 D6, §11).

    One function serves both the gate and submit-revalidation call sites
    (RN-016) — a richer return type means the gate can carry `prefill` while
    submit only reads `.status`, without a second outbound-call function.

    `prefill` is a placeholder (`None`) in this slice — the full
    Portal-shape-to-Hub-shape mapping is Slice C (`prefill.py`). `error_code`
    carries Portal's raw `error_code` for `INTEGRATION_AUTH_FAILURE`
    diagnostics only; it is never surfaced to any Hub API response (RN-010).
    """

    status: PortalFolioStatus
    prefill: Any | None = None
    error_code: str | None = None

    @classmethod
    def eligible(cls, prefill: Any | None = None) -> "PortalGateResult":
        return cls(status=PortalFolioStatus.ELIGIBLE, prefill=prefill)

    @classmethod
    def of(cls, status: PortalFolioStatus, *, error_code: str | None = None) -> "PortalGateResult":
        return cls(status=status, error_code=error_code)


def is_valid_folio_format(folio: str) -> bool:
    """RN-017: validate the folio format before ever calling Portal."""
    return bool(FOLIO_PATTERN.match(folio))


def _masked_folio(folio: str) -> str:
    """RN-018: never log the full folio — keep the prefix and last 4 digits."""
    if len(folio) <= 4:
        return "…"
    return f"{folio[:4]}…-{folio[-4:]}"


def _shape_keys(mapping: Any) -> list[str]:
    """Sorted top-level keys, or [] for a non-mapping. NEVER returns values (§4.1)."""
    return sorted(mapping.keys()) if isinstance(mapping, Mapping) else []


def _build_url(folio: str) -> str:
    path = PORTAL_INTEGRATION_PATH_TEMPLATE.format(folio=folio)
    return f"{settings.PORTAL_API_BASE_URL.rstrip('/')}{path}"


def _request_host(url: str) -> str:
    """Netloc only — no path, no query (§4.1 field list)."""
    return urlsplit(url).netloc


def _extract_error_code(response: httpx.Response) -> str | None:
    """Portal's `error_code` field — never `message` (RN-010: Portal's copy
    carries no stability contract)."""
    try:
        body = response.json()
    except ValueError:
        return None
    return body.get("error_code") if isinstance(body, dict) else None


def _extract_status(response: httpx.Response, folio: str, latency_ms: int) -> PortalFolioStatus:
    body = response.json()
    data = body.get("data") if isinstance(body, dict) else None

    if not isinstance(data, Mapping) or "status" not in data:
        # RN-009: a 200 whose body has no data.status is a CONTRACT VIOLATION,
        # not a rejection. Log keys only (§4.1) — never a value, never PII.
        logger.error(
            "portal_gate.contract_violation folio=%s status_label=%s "
            "received_keys=%s data_keys=%s latency_ms=%d",
            _masked_folio(folio),
            body.get("status_label") if isinstance(body, dict) else None,
            _shape_keys(body),
            _shape_keys(data),
            latency_ms,
        )
        raise PortalUnavailableError(
            f"Portal response for folio {_masked_folio(folio)} is missing "
            "data.status (contract violation)"
        )

    if data.get("status") == PORTAL_ELIGIBLE_STATUS_VALUE:
        return PortalFolioStatus.ELIGIBLE
    return PortalFolioStatus.NOT_ELIGIBLE


def _resolve_success(response: httpx.Response, folio: str, latency_ms: int) -> PortalGateResult:
    status_value = _extract_status(response, folio, latency_ms)
    if status_value == PortalFolioStatus.ELIGIBLE:
        # `prefill=None` this slice — Slice C wires map_lead_prefill() here.
        return PortalGateResult.eligible()
    return PortalGateResult.of(status_value)


def _resolve_auth_failure(
    response: httpx.Response, folio: str, request_host: str, latency_ms: int
) -> PortalGateResult:
    """ANY 401, any error_code, is TERMINAL for the transport loop (design
    §4). The RN-012 re-fire for TIMESTAMP_EXPIRED already happened one layer
    down, inside `PortalHmacAuth.auth_flow` — by the time client.py sees a
    401 here, it is the FINAL response for this attempt."""
    error_code = _extract_error_code(response)
    logger.error(
        "portal_gate.auth_failure folio=%s error_code=%s api_key=%s host=%s latency_ms=%d",
        _masked_folio(folio),
        error_code or "UNKNOWN",
        settings.PORTAL_HUB_API_KEY,
        request_host,
        latency_ms,
    )
    return PortalGateResult.of(PortalFolioStatus.INTEGRATION_AUTH_FAILURE, error_code=error_code)


def validate_folio(folio: str) -> PortalGateResult:
    """Validate a folio's eligibility against the BLOQUE Portal.

    RN-017 format check happens first — malformed folios never trigger a
    network call. Every request is signed via `PortalHmacAuth` (REQ-013
    §4.2/§4.3). Retries only on timeout/connect errors and 5xx/429
    responses, up to settings.PORTAL_RETRY_ATTEMPTS, with a short backoff
    between attempts. 403/404 are deterministic and are never retried.

    ANY 401 (any error_code) is TERMINAL for this loop and resolves to
    `INTEGRATION_AUTH_FAILURE` (design §4, §13.1) — the RN-012 re-fire for
    `TIMESTAMP_EXPIRED` already happened one layer down, inside
    `PortalHmacAuth.auth_flow`, so it never costs a transport-retry slot.
    """
    if not is_valid_folio_format(folio):
        return PortalGateResult.of(PortalFolioStatus.NOT_ELIGIBLE)

    url = _build_url(folio)
    request_host = _request_host(url)
    auth = PortalHmacAuth(settings.PORTAL_HUB_API_KEY, settings.PORTAL_HUB_API_SECRET)
    attempts = _resolved_retry_attempts()

    last_error: Exception | None = None
    for attempt in range(attempts):
        started = time.monotonic()
        try:
            with httpx.Client(
                auth=auth, timeout=httpx.Timeout(5.0, connect=3.0)
            ) as client:
                response = client.get(url)
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            last_error = exc
            logger.warning(
                "Portal gate request failed for folio %s (attempt %d/%d): %s",
                folio, attempt + 1, attempts, exc,
            )
            if attempt < attempts - 1:
                time.sleep(_backoff_seconds(attempt))
                continue
            logger.warning(
                "Portal gate unreachable for folio %s after %d attempts", folio, attempts
            )
            raise PortalUnavailableError(
                f"Portal unreachable after {attempts} attempts"
            ) from exc

        latency_ms = int((time.monotonic() - started) * 1000)

        if response.status_code == 200:
            return _resolve_success(response, folio, latency_ms)
        if response.status_code == 401:
            return _resolve_auth_failure(response, folio, request_host, latency_ms)
        if response.status_code in (403, 404):
            return PortalGateResult.of(PortalFolioStatus.NOT_ELIGIBLE)
        if response.status_code == 429 or response.status_code >= _RETRYABLE_STATUS_THRESHOLD:
            last_error = PortalGateError(
                f"Portal returned {response.status_code}"
            )
            logger.warning(
                "Portal gate returned %d for folio %s (attempt %d/%d)",
                response.status_code, folio, attempt + 1, attempts,
            )
            if attempt < attempts - 1:
                time.sleep(_backoff_seconds(attempt))
                continue
            logger.warning(
                "Portal gate unavailable for folio %s after %d attempts "
                "(last status %d)",
                folio, attempts, response.status_code,
            )
            raise PortalUnavailableError(
                f"Portal unavailable after {attempts} attempts "
                f"(last status {response.status_code})"
            ) from last_error

        # Any OTHER unexpected status is not part of the documented taxonomy
        # (design §4.5) — fail loudly as unavailable rather than guessing.
        logger.warning(
            "Portal gate returned unexpected status %d for folio %s — "
            "treating as unavailable, not a business rejection",
            response.status_code, folio,
        )
        raise PortalUnavailableError(
            f"Portal returned unexpected status {response.status_code}"
        )

    # Unreachable in practice (loop always returns or raises), but keeps mypy happy.
    raise PortalUnavailableError(
        f"Portal unavailable after {attempts} attempts"
    ) from last_error
