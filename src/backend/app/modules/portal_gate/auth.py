"""`httpx.Auth` transport layer for the BLOQUE Portal HMAC contract (REQ-013).

Design reference: openspec/changes/req-013-portal-hmac/design.md §3.

Owns exactly one thing: the RN-012 timestamp-expiry re-fire. It knows nothing
about routes, envelopes, or the `error_code` taxonomy — that lives one layer up,
in `client.py`.
"""

import time
from typing import Callable, Generator

import httpx

from app.modules.portal_gate import signing


class PortalHmacAuth(httpx.Auth):
    # MANDATORY. httpx only reads the response body before handing it back to
    # `auth_flow` when this is True. Without it, `response.json()` inside
    # `_is_timestamp_expired` raises `httpx.ResponseNotRead` and the request
    # dies mid-flight instead of re-firing. Do not remove — see
    # test_refire_without_requires_response_body_crashes_loudly.
    requires_response_body = True

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._now = now

    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        # D8: the re-fire budget is enforced by this generator's shape —
        # exactly one conditional second `yield`, no instance-level counter
        # to reset (and therefore nothing to leak across requests).
        self._apply_signature(request)
        response = yield request
        if self._is_timestamp_expired(response):
            self._apply_signature(request)  # fresh ts + fresh signature (RN-006)
            yield request

    def _apply_signature(self, request: httpx.Request) -> None:
        timestamp = signing.current_timestamp(self._now)
        # RN-003: signed from the bytes httpx will actually transmit, after
        # client-side normalization — never a string reconstructed elsewhere.
        path = signing.path_without_query(request.url.raw_path)
        canonical = signing.canonical_string(request.method, path, timestamp)
        request.headers[signing.API_KEY_HEADER] = self._api_key
        request.headers[signing.TIMESTAMP_HEADER] = timestamp
        request.headers[signing.SIGNATURE_HEADER] = signing.sign(
            self._api_secret, canonical
        )

    @staticmethod
    def _is_timestamp_expired(response: httpx.Response) -> bool:
        """True only for a 401 whose body's `error_code` is TIMESTAMP_EXPIRED (RN-012).

        Any other 401 (or any other status) is terminal for this layer.
        """
        if response.status_code != 401:
            return False
        try:
            body = response.json()
        except ValueError:
            return False
        return isinstance(body, dict) and body.get("error_code") == "TIMESTAMP_EXPIRED"
