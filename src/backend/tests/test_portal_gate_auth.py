"""TDD: `httpx.Auth` transport layer for the BLOQUE Portal HMAC contract.

Design reference: openspec/changes/req-013-portal-hmac/design.md §3.

Every test here drives `PortalHmacAuth` with a bare `httpx.Client` + a
`MockTransport`. None of them build or call `client.py::validate_folio` — RN-003
and RN-006/RN-012 are properties of this layer alone, so a test that needed
`client.py` to pass would be testing the wrong thing.
"""

import itertools
import json

import httpx
import pytest

from app.modules.portal_gate import signing
from app.modules.portal_gate.auth import PortalHmacAuth

API_KEY = "test-api-key"
API_SECRET = "test-api-secret"
_URL = "https://portal.example/api/integrations/bloque-hub/leads/BCE-20260715-172822-2973/access"
_ELIGIBLE_BODY = {"data": {"status": "quotation_in_progress"}}


def test_auth_declares_requires_response_body():
    # A literal class-attribute assertion, not a behavioural one — the
    # behavioural re-fire test below can pass for the wrong reason if httpx
    # ever changes its response-buffering defaults.
    assert PortalHmacAuth.requires_response_body is True


def test_signed_path_matches_wire_path():
    def handler(request: httpx.Request) -> httpx.Response:
        # Recompute the signature from the RECEIVED request, never from a
        # string reconstructed on the test side (RN-003 proven, not assumed).
        path = signing.path_without_query(request.url.raw_path)
        timestamp = request.headers[signing.TIMESTAMP_HEADER]
        canonical = signing.canonical_string(request.method, path, timestamp)
        expected_signature = signing.sign(API_SECRET, canonical)
        assert request.headers[signing.SIGNATURE_HEADER] == expected_signature
        return httpx.Response(200, json=_ELIGIBLE_BODY)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, auth=PortalHmacAuth(API_KEY, API_SECRET)) as client:
        response = client.get(_URL)

    assert response.status_code == 200


def test_percent_encoded_path_is_signed_as_transmitted():
    # Deliberately bypasses validate_folio/FOLIO_PATTERN — that format makes
    # this case unreachable through the client, but RN-003 must hold
    # independently of the folio format, so it is driven directly here.
    encoding_sensitive_url = (
        "https://portal.example/api/integrations/bloque-hub/leads/BCE 2026 x/access"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert b"%20" in request.url.raw_path  # percent-encoding present on the wire
        path = signing.path_without_query(request.url.raw_path)
        timestamp = request.headers[signing.TIMESTAMP_HEADER]
        canonical = signing.canonical_string(request.method, path, timestamp)
        expected_signature = signing.sign(API_SECRET, canonical)
        assert request.headers[signing.SIGNATURE_HEADER] == expected_signature
        return httpx.Response(200, json=_ELIGIBLE_BODY)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, auth=PortalHmacAuth(API_KEY, API_SECRET)) as client:
        response = client.get(encoding_sensitive_url)

    assert response.status_code == 200


def test_refire_fires_exactly_once_on_timestamp_expired():
    # Every response is TIMESTAMP_EXPIRED, so this also proves D8: the budget
    # is enforced by auth_flow's shape (exactly two yields), not a counter —
    # a third attempt never happens even when the second one also expires.
    calls: list[tuple[str, str]] = []
    fake_clock = itertools.count(1767225600, step=5)

    def handler(request: httpx.Request) -> httpx.Response:
        # Snapshot the two header values now — `request` is the SAME mutable
        # object across both yields (auth_flow re-signs it in place), so
        # holding a reference to `request.headers` itself would make both
        # list entries alias the second attempt's values.
        calls.append(
            (
                request.headers[signing.TIMESTAMP_HEADER],
                request.headers[signing.SIGNATURE_HEADER],
            )
        )
        return httpx.Response(401, json={"error_code": "TIMESTAMP_EXPIRED"})

    transport = httpx.MockTransport(handler)
    auth = PortalHmacAuth(API_KEY, API_SECRET, now=lambda: next(fake_clock))
    with httpx.Client(transport=transport, auth=auth) as client:
        response = client.get(_URL)

    assert response.status_code == 401
    assert len(calls) == 2
    # RN-006 / "no signature reuse across attempts": fresh timestamp AND
    # fresh signature on the re-fire, never the first attempt's values.
    assert calls[0][0] != calls[1][0]  # timestamp
    assert calls[0][1] != calls[1][1]  # signature


def test_refire_not_triggered_by_other_401_error_codes():
    # RN-012: only TIMESTAMP_EXPIRED re-fires. Any other 401 error_code is
    # terminal for this layer after exactly one attempt.
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(401, json={"error_code": "INVALID_SIGNATURE"})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, auth=PortalHmacAuth(API_KEY, API_SECRET)) as client:
        response = client.get(_URL)

    assert response.status_code == 401
    assert len(calls) == 1


class _UnconsumedJSONStream(httpx.SyncByteStream):
    """Yields bytes only when iterated, mimicking a real not-yet-read network
    response body. `httpx.Response(json=...)` reads content eagerly at
    construction time (any ByteStream is read in `Response.__init__`), which
    would make `requires_response_body` a no-op for a MockTransport-driven
    test — this class is what makes the regression reproducible.
    """

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __iter__(self):
        yield self._payload


def test_refire_without_requires_response_body_crashes_loudly():
    # Regression test verified against the installed httpx 0.28.1: dropping
    # `requires_response_body` does NOT make the re-fire quietly skip.
    # `response.json()` inside `_is_timestamp_expired` raises
    # `httpx.ResponseNotRead` and the whole request dies — a loud crash, not
    # a silently-skipped re-fire. Protects the mandatory flag from a
    # "harmless-looking" removal.
    class _NoResponseBodyAuth(PortalHmacAuth):
        requires_response_body = False

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.dumps({"error_code": "TIMESTAMP_EXPIRED"}).encode("utf-8")
        return httpx.Response(
            401,
            headers={"content-type": "application/json"},
            stream=_UnconsumedJSONStream(payload),
        )

    transport = httpx.MockTransport(handler)
    auth = _NoResponseBodyAuth(API_KEY, API_SECRET)
    with httpx.Client(transport=transport, auth=auth) as client:
        with pytest.raises(httpx.ResponseNotRead):
            client.get(_URL)
