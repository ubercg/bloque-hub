"""TDD: pure signing primitives for the BLOQUE Portal HMAC contract (REQ-013 §4.3).

Design reference: openspec/changes/req-013-portal-hmac/design.md §3.

These tests never import httpx and never build a request — `signing.py` is bytes
and strings only, so a break here can never be masked by the transport layer.
"""

import re

from app.modules.portal_gate import signing

# Known vector — computed independently with a standalone `python -c` one-liner
# from REQ-013 §4.3 (canonical = METHOD + "\n" + PATH + "\n" + TIMESTAMP,
# signature = base64(hmac_sha256_raw(secret, canonical))), NEVER by running the
# implementation under test. A vector derived from the code being tested would
# only prove the code equals itself.
_KNOWN_SECRET = "test-secret-vector"
_KNOWN_METHOD = "GET"
_KNOWN_PATH = "/api/integrations/bloque-hub/leads/BCE-20260715-172822-2973/access"
_KNOWN_TIMESTAMP = "1767225600"
_KNOWN_SIGNATURE = "cVq1YbWSfBtJ6/9/LrBEwU33gazDGTxcKE3Bi7o3ITA="


def test_known_vector():
    canonical = signing.canonical_string(_KNOWN_METHOD, _KNOWN_PATH, _KNOWN_TIMESTAMP)
    assert canonical == f"{_KNOWN_METHOD}\n{_KNOWN_PATH}\n{_KNOWN_TIMESTAMP}"
    assert signing.sign(_KNOWN_SECRET, canonical) == _KNOWN_SIGNATURE


def test_timestamp_is_digits_only_utc_seconds():
    # RN-005: unix epoch seconds, UTC, digits-only string. `now` is injectable
    # so the test is deterministic instead of racing the real clock.
    fixed_epoch_seconds = 1767225600.789

    timestamp = signing.current_timestamp(now=lambda: fixed_epoch_seconds)

    assert timestamp == "1767225600"
    assert re.fullmatch(r"\d+", timestamp)


def test_path_without_query_strips_query_string():
    # RN-004: httpx `URL.raw_path` is path AND query as bytes. A no-op today
    # (the endpoint is a parameterless GET) but tested so it can never be
    # silently reintroduced.
    raw_path = b"/api/integrations/bloque-hub/leads/BCE-20260715-172822-2973/access?foo=bar"

    assert signing.path_without_query(raw_path) == (
        "/api/integrations/bloque-hub/leads/BCE-20260715-172822-2973/access"
    )


def test_path_without_query_no_query_string_is_unchanged():
    raw_path = b"/api/integrations/bloque-hub/leads/BCE-20260715-172822-2973/access"

    assert signing.path_without_query(raw_path) == (
        "/api/integrations/bloque-hub/leads/BCE-20260715-172822-2973/access"
    )
