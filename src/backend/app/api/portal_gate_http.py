"""HTTP status mapping for `PortalFolioStatus` (REQ-013, design.md §5, §13.1).

Single shared helper used by BOTH the gate (`validate_quote_request_folio`)
and submit-revalidation call sites (RN-016). This is deliberately not a
per-site `if/else` — an `else` branch is exactly how the pre-B2 code
silently mapped a newly introduced status to `403 FOLIO_NOT_ELIGIBLE`. An
unmapped `PortalFolioStatus` member here fails LOUDLY (`500`), never
silently as a business rejection.

Non-negotiable ordering constraint (design §13.1): the `INTEGRATION_AUTH_
FAILURE` enum member (`portal_gate/client.py`), this module, and BOTH
`public.py` call-site switches merge in the SAME commit. Reverting only this
file while leaving the enum member in place recreates the exact bug this
change exists to prevent.
"""

import logging

from fastapi import HTTPException, status

from app.modules.portal_gate.client import PortalFolioStatus

logger = logging.getLogger(__name__)

# D1 fallback point (design §5, §14 open question #1). Phase 0.2 verified
# THIS repository's nginx.conf declares neither `proxy_intercept_errors` nor
# `error_page` (only `proxy_pass` at lines 29, 46, 60, 66, 72, 78) — a 502
# reaches the client unmodified from here. The SHARED EDGE PROXY in front of
# this stack lives outside this repository and could not be verified from
# here; see BIT-018 for the open-item note. If it is later confirmed to
# intercept 502s, flip this ONE constant to `status.HTTP_503_SERVICE_
# UNAVAILABLE` and flip the matching `502 → auth_failure` / `503 →
# unavailable` rows of the frontend fallback table (design §7) — a two-line
# change, not a redesign.
PORTAL_AUTH_FAILURE_HTTP_STATUS = status.HTTP_502_BAD_GATEWAY

_GENERIC_SYSTEM_MESSAGE = "Ocurrió un error inesperado. Intenta más tarde."

# RN-003 fixed message (design.md §2.2, §4.4) — same copy public.py used
# before B2; now the single source both call sites read from.
_FOLIO_NOT_ELIGIBLE_MESSAGE = (
    "El folio proporcionado no se encuentra disponible para iniciar una "
    "cotización. Verifica el estatus en BLOQUE Portal."
)
_PORTAL_UNAVAILABLE_MESSAGE = "Portal no disponible, intenta más tarde."

# Frozen verbatim (delivery decision #4, design §7): a SYSTEM FAULT message
# with NO call to action. No "intenta de nuevo", no support contact — the
# applicant's retry cannot fix a credentials/clock problem on Hub's side,
# and there is no alerting to reference (§2.3).
_AUTH_FAILURE_MESSAGE = (
    "No fue posible validar el folio por un problema de configuración del "
    "sistema. El reintento no resolverá este error."
)

_STATUS_TO_ERROR: dict[PortalFolioStatus, tuple[int, str, str]] = {
    PortalFolioStatus.NOT_ELIGIBLE: (
        status.HTTP_403_FORBIDDEN,
        "FOLIO_NOT_ELIGIBLE",
        _FOLIO_NOT_ELIGIBLE_MESSAGE,
    ),
    PortalFolioStatus.UNAVAILABLE: (
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "PORTAL_UNAVAILABLE",
        _PORTAL_UNAVAILABLE_MESSAGE,
    ),
    PortalFolioStatus.INTEGRATION_AUTH_FAILURE: (
        PORTAL_AUTH_FAILURE_HTTP_STATUS,
        "INTEGRATION_AUTH_FAILURE",
        _AUTH_FAILURE_MESSAGE,
    ),
}


def raise_for_portal_status(portal_status: PortalFolioStatus) -> None:
    """No-op on ELIGIBLE; raises `HTTPException` otherwise (RN-011, RN-016).

    An unmapped member fails LOUDLY as a `500 PORTAL_STATUS_UNMAPPED` —
    never silently as `403 FOLIO_NOT_ELIGIBLE`. See
    `test_every_portal_status_is_mapped` / `test_unmapped_status_fails_loudly`.
    """
    if portal_status is PortalFolioStatus.ELIGIBLE:
        return
    try:
        http_status, reason, message = _STATUS_TO_ERROR[portal_status]
    except KeyError as exc:
        logger.error("portal_gate.unmapped_status status=%s", portal_status.value)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"reason": "PORTAL_STATUS_UNMAPPED", "message": _GENERIC_SYSTEM_MESSAGE},
        ) from exc
    raise HTTPException(status_code=http_status, detail={"reason": reason, "message": message})
