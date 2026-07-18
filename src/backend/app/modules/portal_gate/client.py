"""Outbound HTTP client for the BLOQUE Portal folio-access gate (REQ-012).

Design reference: openspec/changes/quote-request-folio/design.md §3, §9 (RISK-4).

This is the ONLY outbound HTTP client in the codebase — kept as a small, isolated
adapter so a future contract change is a one-line update.
"""

import enum
import re
import time

import httpx

from app.core.config import settings

# TODO(REQ-012 RISK-4): confirm against real bloque_portal contract.
# Assumed 200 response body shape: {"status": "<value>"}. The eligible value and
# the key name below are the ONLY things that should need to change once the
# real contract is confirmed.
PORTAL_STATUS_FIELD = "status"
PORTAL_ELIGIBLE_STATUS_VALUE = "quotation_in_progress"

# RN-017: folio format BCE-YYYYMMDD-HHMMSS-RRRR
FOLIO_PATTERN = re.compile(r"^BCE-\d{8}-\d{6}-\d{4}$")

_RETRYABLE_STATUS_THRESHOLD = 500


class PortalFolioStatus(str, enum.Enum):
    ELIGIBLE = "eligible"
    NOT_ELIGIBLE = "not_eligible"
    UNAVAILABLE = "unavailable"


class PortalGateError(Exception):
    """Base error for the Portal gate client."""


class PortalUnavailableError(PortalGateError):
    """Raised when the Portal API is unreachable after retries are exhausted."""


def is_valid_folio_format(folio: str) -> bool:
    """RN-017: validate the folio format before ever calling Portal."""
    return bool(FOLIO_PATTERN.match(folio))


def _build_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    if settings.PORTAL_API_KEY:
        headers["X-Api-Key"] = settings.PORTAL_API_KEY
    return headers


def _extract_status(response: httpx.Response) -> PortalFolioStatus:
    body = response.json()
    status_value = body.get(PORTAL_STATUS_FIELD)
    if status_value == PORTAL_ELIGIBLE_STATUS_VALUE:
        return PortalFolioStatus.ELIGIBLE
    return PortalFolioStatus.NOT_ELIGIBLE


def validate_folio(folio: str) -> PortalFolioStatus:
    """Validate a folio's eligibility against the BLOQUE Portal.

    RN-017 format check happens first — malformed folios never trigger a
    network call. Retries only on timeout/connect errors and 5xx responses,
    up to settings.PORTAL_RETRY_ATTEMPTS, with a short backoff between
    attempts. 403/404 are deterministic and are never retried.
    """
    if not is_valid_folio_format(folio):
        return PortalFolioStatus.NOT_ELIGIBLE

    url = f"{settings.PORTAL_API_BASE_URL.rstrip('/')}/api/public/space-event-requests/access/{folio}"
    headers = _build_headers()
    attempts = settings.PORTAL_RETRY_ATTEMPTS

    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with httpx.Client(timeout=httpx.Timeout(5.0, connect=3.0)) as client:
                response = client.get(url, headers=headers)
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(0.2 * 2**attempt)
                continue
            raise PortalUnavailableError(
                f"Portal unreachable after {attempts} attempts"
            ) from exc

        if response.status_code == 200:
            return _extract_status(response)
        if response.status_code in (403, 404):
            return PortalFolioStatus.NOT_ELIGIBLE
        if response.status_code >= _RETRYABLE_STATUS_THRESHOLD:
            last_error = PortalGateError(
                f"Portal returned {response.status_code}"
            )
            if attempt < attempts - 1:
                time.sleep(0.2 * 2**attempt)
                continue
            raise PortalUnavailableError(
                f"Portal unavailable after {attempts} attempts "
                f"(last status {response.status_code})"
            ) from last_error

        # Any other unexpected status: treat conservatively as not eligible.
        return PortalFolioStatus.NOT_ELIGIBLE

    # Unreachable in practice (loop always returns or raises), but keeps mypy happy.
    raise PortalUnavailableError(
        f"Portal unavailable after {attempts} attempts"
    ) from last_error
