"""Drives portal-mock.py in-process for the REQ-013 RN-019 double.

`portal-mock.py` lives at the repository root (a hyphenated filename, not
importable by name), so it is loaded via
`importlib.util.spec_from_file_location`. These tests exercise ONLY the
handler's decisions (verification order, status codes, error_code bodies) —
never `app.modules.portal_gate.signing`. The expected signatures below are
computed with an independent, inline HMAC implementation (a third reading of
REQ-013 §4.3, separate from both the mock and the backend's signing.py) so
that a bug shared between the mock's re-implementation and the test itself
cannot hide a verification defect.
"""

import base64
import hashlib
import hmac
import importlib.util
import threading
import time
from http.client import HTTPConnection
from pathlib import Path

import pytest

API_KEY_HEADER = "X-Bloque-Api-Key"
TIMESTAMP_HEADER = "X-Bloque-Timestamp"
SIGNATURE_HEADER = "X-Bloque-Signature"

ELIGIBLE_FOLIO_FULL = "BCE-20260715-172822-2973"
ELIGIBLE_FOLIO_NULLS = "BCE-20260716-091500-1010"
ELIGIBLE_FOLIO_LONG_COMENTARIOS = "BCE-20260717-140030-2020"
TERMINAL_FOLIO = "BCE-20260718-101010-3030"
NOT_ELIGIBLE_FOLIO = "BCE-20260719-121212-4040"
UNKNOWN_FOLIO = "BCE-20260720-000000-9999"


def _find_portal_mock_path() -> Path:
    """`/app/portal-mock.py` is the docker-mounted path (see
    docker-compose.override.yml); the parents[3] fallback resolves the repo
    root when pytest ever runs directly on the host instead of in the
    `backend` container."""
    here = Path(__file__).resolve()
    candidates = [Path("/app/portal-mock.py")]
    if len(here.parents) > 3:
        candidates.append(here.parents[3] / "portal-mock.py")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "portal-mock.py not found at any known location: "
        f"{[str(c) for c in candidates]}"
    )


def _load_portal_mock_module():
    spec = importlib.util.spec_from_file_location(
        "portal_mock_under_test", _find_portal_mock_path()
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# REQ-013 §4.3 — independent inline reimplementation, deliberately separate
# from both portal-mock.py's own re-implementation and the backend's
# signing.py. Verified against the known vector in test_known_signature_vector.
def _canonical_string(method: str, path: str, timestamp: str) -> str:
    return f"{method}\n{path}\n{timestamp}"


def _sign(secret: str, canonical: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode("ascii")


@pytest.fixture(scope="module")
def portal_mock_module():
    return _load_portal_mock_module()


@pytest.fixture(scope="module")
def mock_server(portal_mock_module):
    server = portal_mock_module.HTTPServer(("127.0.0.1", 0), portal_mock_module.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def _request(base_url: str, path: str, headers: dict[str, str] | None = None):
    conn = HTTPConnection(base_url, timeout=5)
    try:
        conn.request("GET", path, headers=headers or {})
        response = conn.getresponse()
        body = response.read()
        return response.status, body
    finally:
        conn.close()


def _signed_headers(
    portal_mock_module, path: str, api_key: str | None = None, secret: str | None = None
) -> dict[str, str]:
    api_key = api_key if api_key is not None else portal_mock_module.PORTAL_HUB_API_KEY
    secret = secret if secret is not None else portal_mock_module.PORTAL_HUB_API_SECRET
    timestamp = str(int(time.time()))
    canonical = _canonical_string("GET", path, timestamp)
    return {
        API_KEY_HEADER: api_key,
        TIMESTAMP_HEADER: timestamp,
        SIGNATURE_HEADER: _sign(secret, canonical),
    }


def test_known_signature_vector():
    """REQ-013 §4.3 known vector — sanity check on the inline test helper
    itself, independent of both portal-mock.py and signing.py."""
    canonical = _canonical_string(
        "GET",
        f"/api/integrations/bloque-hub/leads/{ELIGIBLE_FOLIO_FULL}/access",
        "1767225600",
    )
    assert (
        _sign("test-secret-vector", canonical)
        == "cVq1YbWSfBtJ6/9/LrBEwU33gazDGTxcKE3Bi7o3ITA="
    )


def test_unsigned_request_rejected(mock_server):
    status, body = _request(
        mock_server, f"/api/integrations/bloque-hub/leads/{ELIGIBLE_FOLIO_FULL}/access"
    )
    assert status == 401
    assert b"MISSING_CREDENTIALS" in body


def test_partial_headers_rejected(mock_server):
    status, body = _request(
        mock_server,
        f"/api/integrations/bloque-hub/leads/{ELIGIBLE_FOLIO_FULL}/access",
        headers={API_KEY_HEADER: "whatever"},
    )
    assert status == 401
    assert b"MISSING_CREDENTIALS" in body


def test_bad_signature_rejected(mock_server, portal_mock_module):
    path = f"/api/integrations/bloque-hub/leads/{ELIGIBLE_FOLIO_FULL}/access"
    headers = _signed_headers(portal_mock_module, path)
    headers[SIGNATURE_HEADER] = "not-a-real-signature"
    status, body = _request(mock_server, path, headers=headers)
    assert status == 401
    assert b"INVALID_SIGNATURE" in body


def test_valid_signature_returns_200_envelope(mock_server, portal_mock_module):
    path = f"/api/integrations/bloque-hub/leads/{ELIGIBLE_FOLIO_FULL}/access"
    headers = _signed_headers(portal_mock_module, path)
    status, body = _request(mock_server, path, headers=headers)
    assert status == 200
    import json

    payload = json.loads(body)
    assert payload["data"]["status"] == "quotation_in_progress"
    assert payload["data"]["lead_prefill"]["nombre_solicitante"] == "Ana Torres"


def test_unknown_api_key_rejected(mock_server, portal_mock_module):
    path = f"/api/integrations/bloque-hub/leads/{ELIGIBLE_FOLIO_FULL}/access"
    headers = _signed_headers(portal_mock_module, path, api_key="not-the-configured-key")
    status, body = _request(mock_server, path, headers=headers)
    assert status == 401
    assert b"UNKNOWN_API_KEY" in body


def test_malformed_timestamp_rejected(mock_server, portal_mock_module):
    path = f"/api/integrations/bloque-hub/leads/{ELIGIBLE_FOLIO_FULL}/access"
    headers = {
        API_KEY_HEADER: portal_mock_module.PORTAL_HUB_API_KEY,
        TIMESTAMP_HEADER: "not-digits",
        SIGNATURE_HEADER: "irrelevant",
    }
    status, body = _request(mock_server, path, headers=headers)
    assert status == 401
    assert b"MALFORMED_TIMESTAMP" in body


def test_expired_timestamp_rejected(mock_server, portal_mock_module):
    path = f"/api/integrations/bloque-hub/leads/{ELIGIBLE_FOLIO_FULL}/access"
    stale_timestamp = str(int(time.time()) - 301)
    canonical = _canonical_string("GET", path, stale_timestamp)
    headers = {
        API_KEY_HEADER: portal_mock_module.PORTAL_HUB_API_KEY,
        TIMESTAMP_HEADER: stale_timestamp,
        SIGNATURE_HEADER: _sign(portal_mock_module.PORTAL_HUB_API_SECRET, canonical),
    }
    status, body = _request(mock_server, path, headers=headers)
    assert status == 401
    assert b"TIMESTAMP_EXPIRED" in body


def test_unmatched_route_returns_404(mock_server):
    status, body = _request(mock_server, "/api/public/space-event-requests/access/BCE-1")
    assert status == 404
    assert b"FOLIO_NOT_FOUND" in body


def test_unknown_folio_with_valid_signature_returns_404(mock_server, portal_mock_module):
    path = f"/api/integrations/bloque-hub/leads/{UNKNOWN_FOLIO}/access"
    headers = _signed_headers(portal_mock_module, path)
    status, body = _request(mock_server, path, headers=headers)
    assert status == 404
    assert b"FOLIO_NOT_FOUND" in body


def test_terminal_fixture_returns_403(mock_server, portal_mock_module):
    path = f"/api/integrations/bloque-hub/leads/{TERMINAL_FOLIO}/access"
    headers = _signed_headers(portal_mock_module, path)
    status, body = _request(mock_server, path, headers=headers)
    assert status == 403
    assert b"TERMINAL" in body


def test_not_eligible_fixture_returns_403(mock_server, portal_mock_module):
    path = f"/api/integrations/bloque-hub/leads/{NOT_ELIGIBLE_FOLIO}/access"
    headers = _signed_headers(portal_mock_module, path)
    status, body = _request(mock_server, path, headers=headers)
    assert status == 403
    assert b"NOT_ELIGIBLE" in body


def test_all_null_optionals_fixture_returns_200(mock_server, portal_mock_module):
    path = f"/api/integrations/bloque-hub/leads/{ELIGIBLE_FOLIO_NULLS}/access"
    headers = _signed_headers(portal_mock_module, path)
    status, body = _request(mock_server, path, headers=headers)
    assert status == 200
    import json

    prefill = json.loads(body)["data"]["lead_prefill"]
    assert all(value is None for value in prefill.values())


def test_long_comentarios_fixture_exceeds_truncation_limit(mock_server, portal_mock_module):
    path = f"/api/integrations/bloque-hub/leads/{ELIGIBLE_FOLIO_LONG_COMENTARIOS}/access"
    headers = _signed_headers(portal_mock_module, path)
    status, body = _request(mock_server, path, headers=headers)
    assert status == 200
    import json

    comentarios = json.loads(body)["data"]["lead_prefill"]["comentarios"]
    assert len(comentarios) > 5000


def test_query_string_is_stripped_before_route_match(mock_server, portal_mock_module):
    path = f"/api/integrations/bloque-hub/leads/{ELIGIBLE_FOLIO_FULL}/access"
    headers = _signed_headers(portal_mock_module, path)
    status, body = _request(mock_server, f"{path}?utm_source=test", headers=headers)
    assert status == 200
    assert b"quotation_in_progress" in body


def test_folio_pattern_matches_all_fixtures(portal_mock_module):
    """All fixture folios must satisfy FOLIO_PATTERN or the backend never
    calls out (design.md §8)."""
    import re

    folio_pattern = re.compile(r"^BCE-\d{8}-\d{6}-\d{4}$")
    for folio in portal_mock_module.FIXTURES:
        assert folio_pattern.match(folio), f"{folio} does not match FOLIO_PATTERN"
    assert len(portal_mock_module.FIXTURES) >= 5
