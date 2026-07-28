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
from typing import Any, Mapping

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


class PortalGateError(Exception):
    """Base error for the Portal gate client."""


class PortalUnavailableError(PortalGateError):
    """Raised when the Portal API is unreachable after retries are exhausted,
    or when a 200 response violates the REQ-013 §4.4 contract (missing
    `data.status` — RN-009: a contract violation is never a business
    rejection, so it must never resolve to NOT_ELIGIBLE)."""


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


def _extract_status(response: httpx.Response, folio: str) -> PortalFolioStatus:
    body = response.json()
    data = body.get("data") if isinstance(body, dict) else None

    if not isinstance(data, Mapping) or "status" not in data:
        # RN-009: a 200 whose body has no data.status is a CONTRACT VIOLATION,
        # not a rejection. Log keys only (§4.1) — never a value, never PII.
        logger.error(
            "portal_gate.contract_violation folio=%s status_label=%s "
            "received_keys=%s data_keys=%s",
            _masked_folio(folio),
            body.get("status_label") if isinstance(body, dict) else None,
            _shape_keys(body),
            _shape_keys(data),
        )
        raise PortalUnavailableError(
            f"Portal response for folio {_masked_folio(folio)} is missing "
            "data.status (contract violation)"
        )

    if data.get("status") == PORTAL_ELIGIBLE_STATUS_VALUE:
        return PortalFolioStatus.ELIGIBLE
    return PortalFolioStatus.NOT_ELIGIBLE


def validate_folio(folio: str) -> PortalFolioStatus:
    """Validate a folio's eligibility against the BLOQUE Portal.

    RN-017 format check happens first — malformed folios never trigger a
    network call. Every request is signed via `PortalHmacAuth` (REQ-013
    §4.2/§4.3). Retries only on timeout/connect errors and 5xx/429
    responses, up to settings.PORTAL_RETRY_ATTEMPTS, with a short backoff
    between attempts. 403/404 are deterministic and are never retried.

    A 401 of any kind is, for this slice, treated the same as any other
    unexpected status: PortalUnavailableError, no retry (the full
    INTEGRATION_AUTH_FAILURE taxonomy lands in a later slice — see
    design.md §13.1).
    """
    if not is_valid_folio_format(folio):
        return PortalFolioStatus.NOT_ELIGIBLE

    url = _build_url(folio)
    auth = PortalHmacAuth(settings.PORTAL_HUB_API_KEY, settings.PORTAL_HUB_API_SECRET)
    attempts = _resolved_retry_attempts()

    last_error: Exception | None = None
    for attempt in range(attempts):
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

        if response.status_code == 200:
            return _extract_status(response, folio)
        if response.status_code in (403, 404):
            return PortalFolioStatus.NOT_ELIGIBLE
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

        # Any OTHER unexpected status (e.g. 401 from a bad signature/expired
        # clock) is NOT a deterministic business rejection — unlike 403/404,
        # it signals a misconfiguration or transient Portal issue and must
        # not silently masquerade as NOT_ELIGIBLE. The full 401 taxonomy
        # (INTEGRATION_AUTH_FAILURE) is out of scope for this slice.
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
