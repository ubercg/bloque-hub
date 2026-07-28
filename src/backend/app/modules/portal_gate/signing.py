"""Pure HMAC signing primitives for the BLOQUE Portal contract (REQ-013 §4.3).

No httpx import, no config import, no logging. Every function here operates on
plain bytes/strings so it can be tested without a request object, a client, or
network access — the layer immediately above (`auth.py`) is the only thing that
knows about `httpx.Request`.
"""

import base64
import hashlib
import hmac
import time
from typing import Callable

API_KEY_HEADER = "X-Bloque-Api-Key"
TIMESTAMP_HEADER = "X-Bloque-Timestamp"
SIGNATURE_HEADER = "X-Bloque-Signature"

# REQ-013 §4.3 — contract, not cosmetics. Do not change without a spec update.
CANONICAL_SEPARATOR = "\n"


def canonical_string(method: str, path: str, timestamp: str) -> str:
    """METHOD + "\\n" + PATH + "\\n" + TIMESTAMP (REQ-013 §4.3)."""
    return CANONICAL_SEPARATOR.join((method, path, timestamp))


def sign(secret: str, canonical: str) -> str:
    """base64(hmac_sha256_raw(secret, canonical))."""
    digest = hmac.new(
        secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def current_timestamp(now: Callable[[], float] = time.time) -> str:
    """Unix epoch SECONDS, UTC, digits only (RN-005). `now` injectable for tests."""
    return str(int(now()))


def path_without_query(raw_path: bytes) -> str:
    """RN-004: httpx `URL.raw_path` is path AND query as bytes.

    Split on the first b"?" and decode ASCII — `raw_path` is percent-encoded
    ASCII by construction, so a plain ASCII decode never raises.
    """
    path, _, _ = raw_path.partition(b"?")
    return path.decode("ascii")
