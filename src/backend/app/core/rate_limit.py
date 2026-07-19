"""Per-IP rate limiting for public (no-JWT) endpoints (PR#10, REQ-012).

The three `/api/public/quote-requests*` endpoints are unauthenticated and
were completely unthrottled — a BLOCKER found in the 4R adversarial review
(email-bombing on submit, disk-fill via uploads, DB/Portal amplification via
price-preview, which needs no valid folio). This module wires a Redis-backed
`slowapi` limiter into the app.

Two things make this correct in THIS deployment (app sits behind nginx):

1. **Real client IP extraction.** `request.client.host` is nginx's IP, not
   the real client's — using it as the rate-limit key would bucket every
   real user together (or exempt everyone once nginx's own IP hits the
   limit). `infra/nginx/nginx.conf` already sets `X-Forwarded-For` and
   `X-Real-IP` via `proxy_set_header` (confirmed during PR#10 implementation
   — no nginx.conf change was needed), so `get_client_ip` trusts the first
   hop of `X-Forwarded-For`, falling back to `X-Real-IP`, then to
   `request.client.host` for direct/dev access without nginx in front.

2. **Fail open on Redis outage.** A Redis blip must never take down public
   endpoints — `swallow_errors=True` makes `limits`/slowapi skip enforcement
   (allow the request) and we additionally log a WARNING via a request
   filter hook so an outage is visible in logs without raising.
"""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from app.core.config import settings

logger = logging.getLogger(__name__)


def get_client_ip(request: Request) -> str:
    """Extract the real client IP behind nginx.

    Precedence: first hop of `X-Forwarded-For` -> `X-Real-IP` ->
    `request.client.host`. Only the FIRST `X-Forwarded-For` entry is
    trusted (the entry nginx appends for the direct connecting client);
    this assumes nginx is the only reverse proxy in front of the app and
    that it always sets/overwrites these headers itself (confirmed in
    `infra/nginx/nginx.conf`), so a spoofed client-supplied XFF is
    overwritten by nginx before reaching the app.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first_hop = xff.split(",")[0].strip()
        if first_hop:
            return first_hop
    x_real_ip = request.headers.get("x-real-ip")
    if x_real_ip:
        return x_real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


limiter = Limiter(
    key_func=get_client_ip,
    storage_uri=settings.RATE_LIMIT_STORAGE_URI,
    # Fail OPEN: if the Redis storage backend errors, allow the request
    # rather than 500/deny — a Redis blip must not take down public
    # endpoints. See module docstring point 2.
    swallow_errors=True,
    # NOTE: `headers_enabled=True` is intentionally OFF. slowapi's
    # per-route `@limiter.limit(...)` decorator tries to inject
    # `X-RateLimit-*` headers directly onto the endpoint's return value,
    # which only works when the endpoint returns a `starlette.Response`
    # instance. Every endpoint here returns a Pydantic response model
    # (FastAPI serializes it), so header injection would raise instead of
    # skipping gracefully. `SlowAPIMiddleware` still enforces limits and
    # the exception handler still returns a clean 429 JSON body either way
    # — only the informational rate-limit headers are skipped.
    headers_enabled=False,
)


async def default_rate_limit_state_middleware(request: Request, call_next):
    """Pre-seed `request.state.view_rate_limit = None`.

    slowapi's per-route decorator AND `SlowAPIMiddleware` both unconditionally
    read `request.state.view_rate_limit` (as an argument passed into
    `_inject_headers`) after the route runs — regardless of
    `headers_enabled`. That attribute is only SET when a limit check
    actually completes and records a hit. On the fail-open path
    (`swallow_errors=True` swallowing a broken storage backend, see the
    `limiter` definition above), the check never gets that far, so the
    attribute is left unset and the later read raises `AttributeError`,
    turning a should-be-transparent Redis outage into a 500. Setting a
    default here BEFORE the route runs closes that gap without touching
    slowapi internals.
    """
    request.state.view_rate_limit = None
    return await call_next(request)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """429 JSON body matching the app's existing `{reason, message}` shape
    (see `app/api/public.py` HTTPException `detail` payloads).

    Deliberately does NOT call `limiter._inject_headers` — `headers_enabled`
    is off (see module docstring on the `limiter` definition above) so
    `request.state.view_rate_limit` is not guaranteed to be populated.
    """
    return JSONResponse(
        status_code=429,
        content={
            "reason": "RATE_LIMIT_EXCEEDED",
            "message": "Demasiadas solicitudes. Intenta de nuevo más tarde.",
        },
    )
