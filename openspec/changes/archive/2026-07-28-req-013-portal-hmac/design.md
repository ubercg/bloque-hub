# Design — req-013-portal-hmac

**Change:** `req-013-portal-hmac`
**Requirement:** REQ-013 — Real BLOQUE Portal integration: definitive contract and HMAC signing
**Phase:** design
**Date:** 2026-07-28
**Artifact store:** openspec (mirrored in Engram at `sdd/req-013-portal-hmac/design`)
**Inputs:** `openspec/changes/req-013-portal-hmac/proposal.md`, REQ-013 (Obsidian vault), the codebase

> D1–D4 of the proposal and REQ-013 §11 are **settled**. This document designs the *how*.
> Where design-level investigation contradicts an assumption in the proposal, it is called out
> explicitly (see D6) rather than quietly absorbed.

---

## 1. Technical approach

Four seams, each isolated so a change in one cannot corrupt another:

| Seam | Module | Knows about |
| :--- | :--- | :--- |
| **Crypto** | `portal_gate/signing.py` | Bytes and strings. No HTTP, no config, no logging |
| **Transport auth** | `portal_gate/auth.py` | `httpx.Request`/`Response`. Owns the RN-012 re-fire |
| **Protocol** | `portal_gate/client.py` | Route, envelope, `error_code` taxonomy, transport retry loop |
| **Mapping** | `portal_gate/prefill.py`, `api/portal_gate_http.py` | Portal shape → Hub shape; Hub status → HTTP |

The rule that makes this hold: **each layer's failure mode is visible in a test that does not
instantiate the layer above it.** The known-vector test never builds an `httpx.Client`; the auth test
never calls `validate_folio`; the mapping test never touches HTTP.

---

## 2. Architecture decisions

Decisions D1–D4 are inherited from the proposal. D5–D9 are new, surfaced by reading the code.

### D5 — The shared cap constant lives in `app/core/limits.py`, not in `crm`

| | |
| :--- | :--- |
| **Choice** | New `src/backend/app/core/limits.py` exporting `REQUERIMIENTOS_ESPECIALES_MAX_LENGTH = 5000`. Both `crm/schemas.py:193` and `portal_gate/prefill.py` import it |
| **Alternatives** | (a) Declare it in `crm/schemas.py` and import from `portal_gate`. (b) Hard-code `5000` twice |
| **Rationale** | `crm/schemas.py` **already imports** `portal_gate.client.is_valid_folio_format` (`schemas.py:206`). Putting the constant in `crm` and importing it from `portal_gate` creates a genuine import cycle `crm → portal_gate → crm`. A neutral `core` module is the only placement that satisfies D3's "one source of truth" without the cycle. (b) is the bug D3 exists to prevent |

### D6 — `validate_folio` returns a result object; FOUR test files need repair, not two

| | |
| :--- | :--- |
| **Choice** | `validate_folio(folio: str) -> PortalGateResult` (status + prefill + error_code), keeping **one** function for gate and submit (RN-016) |
| **Alternatives** | A second `fetch_lead_prefill(folio)` function — rejected: forks RN-016's single path and doubles the outbound call, against a 60 req/min limit |
| **Rationale** | The gate needs the prefill and the submit revalidation needs only the status; a richer return serves both from one call. Mitigated by `PortalGateResult.eligible(prefill=None)` / `.of(status)` classmethod constructors so each fake edit is one short call |

**Correction to proposal §5.1 — measured, not estimated.** The claim that the `public.py` integration
suites are "unaffected — new coverage, not repair" is wrong, and the blast radius is larger than the
two files the proposal names. Every site that monkeypatches `validate_folio` returns a bare
`PortalFolioStatus`, so it breaks the moment `public.py` reads `result.status`:

| File | `validate_folio` patch sites | Shape |
| :--- | :---: | :--- |
| `tests/test_public_quote_gate.py` | 5 | fakes + spies |
| `tests/test_public_quote_submit.py` | 6 | fakes + spies |
| `tests/test_public_rate_limit.py` | 5 | includes `lambda f: PortalFolioStatus.ELIGIBLE` at `:36` |
| `tests/test_public_quote_email.py` | 1 | `lambda f: PortalFolioStatus.ELIGIBLE` at `:112` |
| **Total** | **17** | 12 fakes returning a bare enum + 5 spy definitions |

The last two files are **not** mentioned anywhere in the proposal or the exploration. They fail with
`AttributeError: 'PortalFolioStatus' object has no attribute 'status'`, which is loud but is still
17 edits nobody budgeted. Size slice C against 17 sites across four files, not 10 lines across two.

### D7 — `comentarios` is renamed at the mapper boundary, so RN-021 becomes structural

| | |
| :--- | :--- |
| **Choice** | `LeadPrefill` has no field named `comentarios`. The mapper reads Portal's `comentarios` key and writes it into `requerimientos_especiales`; the name `comentarios` does not exist past `prefill.py` |
| **Alternatives** | Carry `comentarios` through to the API and let the frontend decide the destination |
| **Rationale** | RN-021 forbids `comentarios → descripcion_evento`. A rule enforced by discipline is a rule waiting to be broken by the next contributor. If the field is *named* `requerimientos_especiales` from the mapper onward, no downstream layer can plausibly route it to `descripcion_evento` — the wrong mapping stops being reachable rather than merely forbidden |

### D8 — The re-fire budget is enforced by the shape of `auth_flow`, not by a counter

| | |
| :--- | :--- |
| **Choice** | `auth_flow` yields once, conditionally yields a second time, and returns. No attempt counter, no instance state |
| **Alternatives** | An instance-level `self._refired` flag on `PortalHmacAuth` |
| **Rationale** | A counter has to be reset, and a reset that is missed leaks the budget across requests. A generator with exactly two `yield` statements cannot fire three times. `PortalHmacAuth` therefore holds **no mutable state**, which is also what makes the "the loop and the re-fire never interact" claim of D2 verifiable rather than aspirational |

### D9 — Missing credentials fail at import of `app.core.config`, with no explicit check

| | |
| :--- | :--- |
| **Choice** | `PORTAL_HUB_API_KEY: str` and `PORTAL_HUB_API_SECRET: str` — annotated, **no default**. `pydantic-settings` then raises `ValidationError` when `Settings()` is constructed at module import |
| **Alternatives** | `str \| None = None` plus a guard in the client, or a FastAPI startup event that asserts |
| **Rationale** | A required field with no default already *is* the fail-fast mechanism; adding a second check would imply the first is unreliable. A `None` default plus a client-side guard fails at the **first request**, meaning a misconfigured deploy passes its health check and looks healthy until an applicant hits the gate. Cost, stated plainly: the pair must be present wherever `app.core.config` is imported — `.env.example`, `tests/conftest.py`, CI, and `docker-compose.override.yml`. That is a slice-A checklist item, not an afterthought |

---

## 3. Signing layer (D4)

### `src/backend/app/modules/portal_gate/signing.py` — pure, no httpx import

```python
API_KEY_HEADER = "X-Bloque-Api-Key"
TIMESTAMP_HEADER = "X-Bloque-Timestamp"
SIGNATURE_HEADER = "X-Bloque-Signature"
CANONICAL_SEPARATOR = "\n"          # REQ-013 §4.3 — contract, not cosmetics

def canonical_string(method: str, path: str, timestamp: str) -> str:
    """METHOD + "\\n" + PATH + "\\n" + TIMESTAMP (REQ-013 §4.3)."""

def sign(secret: str, canonical: str) -> str:
    """base64(hmac_sha256_raw(secret, canonical))."""

def current_timestamp(now: Callable[[], float] = time.time) -> str:
    """Unix epoch SECONDS, UTC, digits only (RN-005). `now` injectable for tests."""

def path_without_query(raw_path: bytes) -> str:
    """RN-004: httpx `URL.raw_path` is path AND query as bytes. Split on the first
    b"?" and decode ASCII. raw_path is percent-encoded ASCII by construction."""
```

`path_without_query` lives here — not in `auth.py` — precisely because it is the refinement most
likely to be forgotten: as a pure function it gets a test that does not need a request object.

### `src/backend/app/modules/portal_gate/auth.py`

```python
class PortalHmacAuth(httpx.Auth):
    # MANDATORY. httpx does not read the response body before handing it to
    # auth_flow unless this is True. Without it `response.json()` raises
    # httpx.ResponseNotRead and the request dies mid-flight. Do not remove.
    requires_response_body = True

    def __init__(self, api_key: str, api_secret: str,
                 now: Callable[[], float] = time.time) -> None: ...

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        self._apply_signature(request)
        response = yield request
        if self._is_timestamp_expired(response):
            self._apply_signature(request)     # fresh ts + fresh signature (RN-006)
            yield request

    def _apply_signature(self, request: httpx.Request) -> None:
        timestamp = signing.current_timestamp(self._now)
        path = signing.path_without_query(request.url.raw_path)
        canonical = signing.canonical_string(request.method, path, timestamp)
        request.headers[signing.API_KEY_HEADER] = self._api_key
        request.headers[signing.TIMESTAMP_HEADER] = timestamp
        request.headers[signing.SIGNATURE_HEADER] = signing.sign(self._api_secret, canonical)

    @staticmethod
    def _is_timestamp_expired(response: httpx.Response) -> bool:
        """401 AND error_code == TIMESTAMP_EXPIRED, and nothing else (RN-012)."""
```

### How byte-identity is *proven*, not assumed (RN-003)

`auth_flow` receives the request object httpx will transmit, after normalization. The signature is
derived from `request.url.raw_path` — the same bytes that form the request line. No path string is
ever reconstructed, so byte-identity is a property of the data flow, not of `FOLIO_PATTERN`.

Two tests, doing different jobs:

| Test | Asserts |
| :--- | :--- |
| `test_signed_path_matches_wire_path` | Inside a `MockTransport` handler, recompute `sign(secret, canonical_string(req.method, req.url.raw_path.split(b"?")[0].decode(), req.headers[TIMESTAMP_HEADER]))` from the **received** request and assert it equals the received `X-Bloque-Signature`. Nothing is reconstructed from the folio |
| `test_percent_encoded_path_is_signed_as_transmitted` | Drives `PortalHmacAuth` directly with a URL containing an encoding-sensitive character. Deliberately bypasses `validate_folio`, because `FOLIO_PATTERN` makes the case unreachable there — the point is to keep RN-003 covered **independently of** the folio format |

### Known-vector test (`tests/test_portal_gate_signing.py`)

Fixed `SECRET`, `METHOD="GET"`, `PATH="/api/integrations/bloque-hub/leads/BCE-20260715-172822-2973/access"`,
`TIMESTAMP="1767225600"` → one hard-coded Base64 literal.

> **Gotcha for apply:** compute that literal with a standalone `python -c` one-liner from REQ-013
> §4.3, **not** by running the implementation. A vector generated from the code under test asserts
> only that the code equals itself and would happily lock in a wrong separator.

Plus `test_auth_declares_requires_response_body` asserting the class attribute literally. The
behavioural re-fire test can pass for the wrong reason if httpx changes its buffering; the attribute
assertion cannot.

> **Correct failure mode, verified against the installed httpx 0.28.1.** Dropping
> `requires_response_body` does **not** make the re-fire quietly skip. `_auth.py:74-85` and
> `_client.py:930-960` never call `response.read()` in that path, so `response.json()` inside
> `_is_timestamp_expired` raises `httpx.ResponseNotRead` and the whole request dies. The mandate is
> unchanged; the regression test must expect a **loud crash**, not a missing second request. Writing
> that test to assert "only one request was sent" would pass for a completely different reason.

---

## 4. Retry topology (D2)

```
validate_folio(folio) -> PortalGateResult
  │
  ├─ RN-017 format check ──── invalid ──→ NOT_ELIGIBLE   (no network call)
  ▼
  for attempt in 1..N          N = clamp(PORTAL_RETRY_ATTEMPTS, 1, 5)   [TRANSPORT LAYER]
  │
  ├── httpx.Client(auth=PortalHmacAuth(...)).get(url)                   [AUTH LAYER]
  │      ├─ sign(ts1) ─→ send ─→ response
  │      ├─ 401 && error_code == TIMESTAMP_EXPIRED ?
  │      │     └─ yes ─→ sign(ts2) ─→ send ─→ response'      exactly once (D8, RN-006)
  │      └─ hands the FINAL response back to the transport layer
  │
  ├─ timeout / ConnectError ─→ backoff, retry; on exhaustion PortalUnavailableError
  ├─ 5xx                    ─→ backoff, retry; on exhaustion PortalUnavailableError
  ├─ 429                    ─→ backoff, retry; on exhaustion PortalUnavailableError
  ├─ 401 (ANY error_code)   ─→ TERMINAL. log portal_gate.auth_failure → INTEGRATION_AUTH_FAILURE
  ├─ 403 / 404              ─→ TERMINAL. → NOT_ELIGIBLE
  └─ 200                    ─→ parse body["data"]["status"]
                                 ├─ key absent ─→ log portal_gate.contract_violation → UNAVAILABLE
                                 ├─ == "quotation_in_progress" ─→ ELIGIBLE + map_lead_prefill(...)
                                 └─ otherwise ─→ NOT_ELIGIBLE
```

**Non-interaction invariants** (each is a test):

1. A re-fire happens *inside* one `client.get(...)`, so it can never increment `attempt`.
2. Any `401` is terminal for the loop ⇒ at most one transport attempt reaches a
   `401` ⇒ a `TIMESTAMP_EXPIRED` path costs **exactly two** HTTP requests worst case, for any `N`.
3. The loop reads `error_code` **only to log it**. Its sole control decision on a `401` is
   "terminal". The auth layer never observes timeouts or `5xx`.
4. `PortalHmacAuth` holds no mutable state (D8), so there is nothing to reset between attempts.

`Retry-After` on `429` is deliberately **not** honoured — the existing `_backoff_seconds` is reused.
REQ-013 does not require it and adding it would grow the loop's surface for no stated benefit.

### 4.1 Log statements (RN-018, REQ-013 §6)

Both markers are net-new conventions with no observability to extend (§2.3), so their **field lists
are the contract** a future alerting requirement will hook into. Specified to the same level as the
truncation log so tests can be written against them.

```python
# 401, any error_code — terminal for the transport loop
logger.error(
    "portal_gate.auth_failure folio=%s error_code=%s api_key=%s host=%s latency_ms=%d",
    _masked_folio(folio),        # RN-018: truncated folio, never the full value
    error_code or "UNKNOWN",     # from body["error_code"]; never body["message"] (RN-010)
    settings.PORTAL_HUB_API_KEY, # public identifier — explicitly permitted by RN-018
    request_host,                # netloc of PORTAL_API_BASE_URL, no path, no query
    latency_ms,
)

# 200 whose body has no data.status — contract violation, NOT a rejection (RN-009)
logger.error(
    "portal_gate.contract_violation folio=%s status_label=%s received_keys=%s "
    "data_keys=%s latency_ms=%d",
    _masked_folio(folio),
    _safe_status_label(body),    # diagnostic only; never rendered (RN-010, §10 row 3)
    sorted(body.keys()),                            # KEYS ONLY
    sorted(body.get("data", {}).keys()),            # KEYS ONLY
    latency_ms,
)
```

**The keys-only mechanism, made structural.** `sorted(mapping.keys())` is the only expression that
ever touches the violating body. No `%r` of `body`, no `json.dumps(body)`, no f-string interpolating
a value. A helper enforces it and is the single place a test can pin:

```python
def _shape_keys(mapping: Any) -> list[str]:
    """Sorted top-level keys, or [] for a non-mapping. NEVER returns values."""
    return sorted(mapping.keys()) if isinstance(mapping, Mapping) else []
```

| Marker | Level | Fields present | Fields **forbidden** |
| :--- | :--- | :--- | :--- |
| `portal_gate.auth_failure` | `error` | masked folio, `error_code`, `api_key`, target host, latency | secret, `X-Bloque-Signature`, canonical string, timestamp header, full folio, Portal's `message` |
| `portal_gate.contract_violation` | `error` | masked folio, `status_label`, top-level keys, `data` keys, latency | secret, signature, canonical string, **any body value other than `status_label`**, lead PII |
| `portal_gate.prefill_truncated` | `info` | masked folio, original length, limit | the text itself (§6) |
| `portal_gate.prefill_degraded` | `warning` | masked folio, `_shape_keys(raw)` | any prefill value |
| `portal_gate.unmapped_status` | `error` | the unmapped enum value | — |

`status_label` is the single deliberate exception in the contract-violation log: REQ-013 §4.4 and the
DoD require it to be logged for diagnosis while RN-010 forbids rendering it. §10 row 3 keeps it out
of `PortalGateResult`, so logging is the **only** place it can appear.

**Tests** (`caplog`, slice B2): assert each marker fires on its trigger; assert
`settings.PORTAL_HUB_API_SECRET`, the literal `X-Bloque-Signature`, and the canonical separator
`"\n"`-joined string appear in **no** emitted record across the whole client suite; assert a
contract-violation record contains the key names of a PII-bearing body and **none** of its values.

---

## 5. Error contract (D1)

### `src/backend/app/api/portal_gate_http.py` (new)

```python
PORTAL_AUTH_FAILURE_HTTP_STATUS = status.HTTP_502_BAD_GATEWAY   # ← D1 fallback = this one line

_STATUS_TO_ERROR: dict[PortalFolioStatus, tuple[int, str, str]] = {
    PortalFolioStatus.NOT_ELIGIBLE:             (403, "FOLIO_NOT_ELIGIBLE", _FOLIO_NOT_ELIGIBLE_MESSAGE),
    PortalFolioStatus.UNAVAILABLE:              (503, "PORTAL_UNAVAILABLE", _PORTAL_UNAVAILABLE_MESSAGE),
    PortalFolioStatus.INTEGRATION_AUTH_FAILURE: (PORTAL_AUTH_FAILURE_HTTP_STATUS,
                                                 "INTEGRATION_AUTH_FAILURE", _AUTH_FAILURE_MESSAGE),
}

def raise_for_portal_status(portal_status: PortalFolioStatus) -> None:
    """No-op on ELIGIBLE; raises HTTPException otherwise. RN-011 + RN-016."""
    if portal_status is PortalFolioStatus.ELIGIBLE:
        return
    try:
        http_status, reason, message = _STATUS_TO_ERROR[portal_status]
    except KeyError as exc:                       # unmapped member — fail LOUDLY
        logger.error("portal_gate.unmapped_status status=%s", portal_status.value)
        raise HTTPException(500, detail={"reason": "PORTAL_STATUS_UNMAPPED",
                                         "message": _GENERIC_SYSTEM_MESSAGE}) from exc
    raise HTTPException(status_code=http_status, detail={"reason": reason, "message": message})
```

Both `public.py:144` and `public.py:545` become:

```python
try:
    result = portal_gate_client.validate_folio(folio)
except PortalUnavailableError:
    raise_for_portal_status(PortalFolioStatus.UNAVAILABLE)
raise_for_portal_status(result.status)
```

The `if portal_status != PortalFolioStatus.ELIGIBLE:` catch-all disappears from both sites. This is
the RN-016 trap of proposal §3, the failure mode is not that someone writes a wrong mapping, it is
that someone adds an enum member and the existing `else` silently swallows it.

**Unmapped members fail loudly twice, on purpose:**

| Layer | Mechanism |
| :--- | :--- |
| Test time | `test_every_portal_status_is_mapped`: `set(PortalFolioStatus) == {ELIGIBLE} | set(_STATUS_TO_ERROR)`. Adding a member without a mapping turns the suite red |
| Run time | `KeyError` → `500 PORTAL_STATUS_UNMAPPED` + `portal_gate.unmapped_status`. A visible 500 is honest; a `403 FOLIO_NOT_ELIGIBLE` is a lie about the applicant's folio |

`detail.reason` value set (Hub's own namespace, unchanged except for the last row):

| `reason` | HTTP | Meaning |
| :--- | :---: | :--- |
| `INVALID_FOLIO_FORMAT` | 422 | RN-017 format check, pre-network |
| `FOLIO_NOT_ELIGIBLE` | 403 | Portal says no. Retry will not help |
| `PORTAL_UNAVAILABLE` | 503 | Transient. Retry invited |
| `INTEGRATION_AUTH_FAILURE` | **502** | Hub's credentials/clock are wrong. Retry will not help |
| `PORTAL_STATUS_UNMAPPED` | 500 | Programming error. Should never reach production |

**The `503` fallback (proposal risk #1).** `infra/nginx/nginx.conf` sets neither
`proxy_intercept_errors` nor `error_page` (verified: only `proxy_pass` at lines 29, 46, 60, 66, 72,
78). The shared edge proxy lives outside this repository and cannot be verified from here. Because
`detail.reason` is the authoritative discriminator, reverting to `503` is editing
`PORTAL_AUTH_FAILURE_HTTP_STATUS` — one constant, and no frontend *logic* changes.

> **Precision on "zero frontend changes".** The frontend status-code **fallback** table (§7) has
> separate `502 → auth_failure` and `503 → unavailable` rows. Flipping the backend constant without
> flipping that table leaves it internally inconsistent — harmless while `reason` is populated,
> because step 1 of `resolveGateFailure` never reaches the fallback, but it is dead-wrong code
> waiting for the day `reason` goes missing. The fallback is a **two-line** change, not a zero-line
> one: the backend constant plus that row. State it honestly rather than discovering it later.

---

## 6. `lead_prefill` mapping and truncation boundary (D3)

### `src/backend/app/modules/portal_gate/prefill.py` (new)

```python
@dataclass(frozen=True, slots=True)
class LeadPrefill:
    nombre_completo: str | None
    cargo_puesto: str | None
    institucion_organizacion: str | None
    correo_institucional: str | None
    telefono_contacto: str | None
    asistentes_estimados: int | None
    fecha_tentativa: str | None            # ISO date, REFERENCE ONLY (RN-022)
    tipo_evento_sugerido: str | None       # frequently null (RN-014)
    espacio_requerido: str | None          # REFERENCE ONLY, never a space_id (RN-015)
    requerimientos_especiales: str | None  # from Portal `comentarios` (D7, RN-021)
    como_conociste_bloque: str | None
    # `ciudad` intentionally NOT mapped — REQ-013 §4.6, proposal §7.3

TRUNCATION_MARKER = "… [texto recortado]"

def map_lead_prefill(raw: Mapping[str, Any] | None, *, folio: str) -> LeadPrefill:
    """Best-effort, NEVER raises (RN-013). A malformed payload degrades to all-None
    and logs portal_gate.prefill_degraded — it does NOT change the folio status."""

def _truncate(value: str, limit: int) -> tuple[str, bool]:
    """Marker counted INSIDE the budget: len(result) <= limit always."""
    if len(value) <= limit:
        return value, False
    return value[: limit - len(TRUNCATION_MARKER)].rstrip() + TRUNCATION_MARKER, True
```

| Aspect | Decision |
| :--- | :--- |
| Cap constant | `app.core.limits.REQUERIMIENTOS_ESPECIALES_MAX_LENGTH` (D5), imported by `prefill.py` **and** `crm/schemas.py:193`. `Field(None, max_length=REQUERIMIENTOS_ESPECIALES_MAX_LENGTH)` |
| Marker | Counted inside the budget, so the truncated value still passes the submit schema. Spanish, because it is user-visible copy inside a Spanish form |
| Invariant | `len(_truncate(v, limit)[0]) <= limit` for every input. Tested at lengths `limit-1`, `limit`, `limit+1`, `3*limit` |
| Log | `logger.info("portal_gate.prefill_truncated folio=%s original_length=%d limit=%d", _masked_folio(folio), len(value), limit)` — **length only, never content** (RN-018) |
| Folio in logs | `_masked_folio(folio) -> "BCE-…-2973"` (RN-018 "folio truncado") |
| Editability | Untouched. The value lands in a normal store field (RN-013) |

**Failure-boundary distinction, stated so it is not blurred later:** a missing `data.status` is a
contract violation → `UNAVAILABLE` (RN-009). A malformed or partly-garbage `lead_prefill` is
**not** — it degrades to `None`s and the folio still unlocks. Prefill is best-effort; eligibility is
not.

### API surface

`FolioValidateResponse` grows `lead_prefill: LeadPrefillOut | None` (a flat Pydantic mirror of
`LeadPrefill`). It is populated **only** on the successful gate response for the folio just queried.
It never appears on any error detail, never on `QuoteRequestSubmitResponse`, and never in a log
(risk #7). Test: assert `lead_prefill` is absent from the body of every 422/403/502/503 path.

---

## 7. Frontend design

### Store — `features/quote-wizard/store/quote-wizard.store.ts`

Const-object + extracted type, per the loaded TypeScript skill, so the state list has one source of
truth and is exhaustively checkable:

```typescript
export const GATE_STATUS = {
  IDLE: 'idle', LOADING: 'loading', UNLOCKED: 'unlocked',
  INVALID_FORMAT: 'invalid_format', NOT_ELIGIBLE: 'not_eligible', UNAVAILABLE: 'unavailable',
  AUTH_FAILURE: 'auth_failure',      // NEW — INTEGRATION_AUTH_FAILURE
  UNKNOWN_ERROR: 'unknown_error',    // NEW — replaces the not_eligible catch-all
} as const;
export type GateStatus = (typeof GATE_STATUS)[keyof typeof GATE_STATUS];
```

New state and action:

```typescript
leadPrefill: LeadPrefill | null;
fechaTentativa: string | null;        // Step 2 reference display (RN-022)
espacioRequerido: string | null;      // Step 2 reference display (RN-015)
hydrateFromPrefill: (prefill: LeadPrefill) => void;
```

`hydrateFromPrefill` writes every target field in **one** `set(...)` call. That is the reason a bulk
action exists instead of eleven `setField` calls: one store update, one render pass. Rules baked into
it:

- Only non-`null` incoming values are written; a `null` leaves the current value untouched (RN-013,
  and it also means re-hydration cannot clobber text the applicant already typed).
- `tipo_evento_sugerido` / `como_conociste_bloque` are applied **only** if the value is a member of
  `TIPO_EVENTO_OPTIONS` / `COMO_CONOCISTE_OPTIONS` (`features/quote-wizard/constants.ts`). A
  non-member is dropped silently — RN-014 says that is normal, not an error.
- It never writes `descripcionEvento`. Test: `hydrateFromPrefill` leaves `descripcionEvento` at `''`
  even when the prefill carries a long text (RN-021 made structural on the frontend too).
- The three new fields are added to `initialState` so `reset()` clears them.

### `app/(public-wizard)/solicitud/page.tsx`

Two pure helpers in `features/quote-wizard/gate-error.ts` (new), so the branching is testable without
rendering:

```typescript
export function readGateError(err: unknown): { status?: number; reason?: string };
export function resolveGateFailure(status?: number, reason?: string): [GateStatus, string];
```

`resolveGateFailure` precedence — `reason` first, status code second, `unknown_error` last:

| Step | Rule |
| :---: | :--- |
| 1 | `reason` matches a known `GATE_REASON` member → its state + its message (**authoritative**) |
| 2 | else by status: `422 → invalid_format`, `403 → not_eligible`, `503 → unavailable`, `502 → auth_failure` |
| 3 | else → `GATE_STATUS.UNKNOWN_ERROR` + `GENERIC_ERROR_MESSAGE`. **Never `not_eligible`** |

Step 3 is the fix for `page.tsx:60-61`. A dropped connection stops being recorded as a folio
rejection.

> The step-2 row `502 → auth_failure` is coupled to `PORTAL_AUTH_FAILURE_HTTP_STATUS`. If the D1
> fallback is exercised, this row becomes `503 → auth_failure` and the `503 → unavailable` row is
> dropped. Add the same cross-reference as a code comment so the coupling is visible from both ends.

Success path: `if (data.lead_prefill) hydrateFromPrefill(data.lead_prefill);` **before**
`setGateStatus(UNLOCKED)` and `router.push`, so Step 3 mounts already filled.

Auth-failure copy — system fault, no call to action, and it must not claim an alert was raised
(§2.3: there is no alerting):

```typescript
const AUTH_FAILURE_MESSAGE =
  'No pudimos validar tu folio por una falla de configuración en la integración con BLOQUE Portal. ' +
  'Reintentar no resolverá el problema.';
```

React 19 with the React Compiler: **no `useMemo`/`useCallback` anywhere** in the touched components.
Zustand selectors stay one-field-per-hook, matching the existing file; `useShallow` only if a
component genuinely needs several fields at once.

### Step 3 and Step 2

- **Step 3 (`StepSolicitante.tsx`) needs no change.** Its inputs are already controlled from the same
  store keys `hydrateFromPrefill` writes, so hydration before navigation produces a pre-filled and
  fully editable form for free. Do not add an effect.
- **Step 2 (`StepEspacio.tsx`)** renders a read-only informational block when `fechaTentativa` or
  `espacioRequerido` is non-null — plain `<p>` text, not bound to any input. Explicit prohibition:
  no effect may feed these into `addItem`, into a date default, or into a `space_id` lookup
  (RN-015, RN-022).

New file `features/quote-wizard/gate-error.ts` must not import from `app/`. **This is a convention,
not an enforced rule** — `.dependency-cruiser.cjs` has exactly two rules: `app/` must not deep-import
`features/*/{components,store,lib}`, and `lib/` (excluding `lib/store`) must not import `features/`.
Neither constrains `features/ → app/`, so `npm run verify:deps` will **not** catch a violation here.
Adding that third rule would be a real improvement but is out of scope for REQ-013; do not claim
tooling coverage that does not exist.

---

## 8. Test double (RN-019) — `portal-mock.py`

Stdlib only: `http.server`, `hmac`, `hashlib`, `base64`, `time`, `json`, `os`, `re`. No backend
import, no shared package.

**How the canonical string is shared as a *definition*, not as code.** The double re-implements
`canonical = f"{method}\n{path}\n{timestamp}"` from REQ-013 §4.3. Both implementations carry the same
`REQ-013 §4.3` citation and the same known vector as a comment. The proof that they agree is the
compose smoke: the backend signs, the double verifies independently, and if the two readings of the
contract diverge the smoke fails with `401 INVALID_SIGNATURE`. A double that imported the backend's
`signing.py` would agree with it by construction and would therefore prove nothing.

Verification order — credential checks **before** folio lookup, so an unsigned request cannot learn
whether a folio exists:

| # | Check | Failure |
| :---: | :--- | :--- |
| 1 | Path matches `^/api/integrations/bloque-hub/leads/(?P<folio>[^/?]+)/access$` (query stripped first) | `404 FOLIO_NOT_FOUND` |
| 2 | All three `X-Bloque-*` headers present | `401 MISSING_CREDENTIALS` |
| 3 | `X-Bloque-Api-Key` equals the configured key | `401 UNKNOWN_API_KEY` |
| 4 | `X-Bloque-Timestamp` is digits only | `401 MALFORMED_TIMESTAMP` |
| 5 | `abs(now - int(ts)) <= 300` | `401 TIMESTAMP_EXPIRED` |
| 6 | `hmac.compare_digest(expected, received)` | `401 INVALID_SIGNATURE` |
| 7 | Folio fixture lookup | `200` envelope / `403 NOT_ELIGIBLE` / `403 TERMINAL` / `404 FOLIO_NOT_FOUND` |

Constant-time comparison at step 6 even in a double: it is the reference reader of the contract, and
a sloppy double teaches sloppy expectations. Rate limiting is deliberately not implemented.

Fixtures: at least one eligible folio with a full `lead_prefill`, one with every optional key `null`,
one whose `comentarios` exceeds 5000 characters (exercises D3 locally), one `403 TERMINAL`, one
`403 NOT_ELIGIBLE`. All fixture folios must satisfy `FOLIO_PATTERN` or the backend never calls out.

`docker-compose.override.yml`: add the `PORTAL_HUB_API_KEY` / `PORTAL_HUB_API_SECRET` pair to **both**
the `backend` and `portal-mock` services with matching obviously-fake dev values, and a comment
stating that this file is committed, that these are local-double credentials only, and that RN-020
forbids reusing them in any other environment.

---

## 9. Config and secrets

| Setting | Shape | Note |
| :--- | :--- | :--- |
| `PORTAL_HUB_API_KEY` | `str`, **no default** | Public identifier |
| `PORTAL_HUB_API_SECRET` | `str`, **no default** | Secret. Secrets manager only |
| `PORTAL_API_BASE_URL` | unchanged | Distinct from `PORTAL_BASE_URL` (display link) — do not conflate |
| `PORTAL_RETRY_ATTEMPTS` | unchanged | Still clamped 1–5 |
| `PORTAL_API_KEY` | **deleted** | See §10 |

Fail-fast is D9: no default ⇒ `Settings()` raises at import of `app.core.config`, i.e. at process
start. Companion edits, all in slice A:

- `.env.example` — both keys with dev-double values.
- `src/backend/tests/conftest.py` — `os.environ.setdefault(...)` at the top, **before** any `app.*`
  import. The file already uses this pattern for `DATABASE_URL` (lines 7-11).
- CI environment and the deploy environment (per environment, RN-020).

RN-017 is preserved by construction: the credentials are read only in `config.py` and passed only to
`PortalHmacAuth`. Three verifications, because a source grep alone is not enough:

| # | Check | Command / mechanism |
| :---: | :--- | :--- |
| 1 | No credential-shaped field on any response model | Test: `FolioValidateResponse.model_fields` and `LeadPrefillOut.model_fields` contain no key matching `api_key\|secret\|signature` |
| 2 | The secret appears in no API response body | Test: assert the configured secret is not a substring of the serialized body on every gate/submit path, success and error |
| 3 | **The secret is absent from the built frontend bundle** | `npm run build` in `src/frontend`, then grep the emitted `.next/` output (`.next/static`, `.next/server`) for the secret value and for the literals `PORTAL_HUB_API_SECRET` / `PORTAL_HUB_API_KEY`. Zero hits required |

Check 3 is the one the DoD actually asks for and the one a `src/` grep cannot give: a build can inline
a value that never appears verbatim in source (via `NEXT_PUBLIC_` promotion, a config spread, or an
env passthrough in `next.config.ts`). Grepping source proves nobody *typed* the secret; grepping the
bundle proves nobody *shipped* it. Run it in CI after the build step, or record it in the bitácora as
a release check if CI has no frontend build stage.

---

## 10. Removals — what must stop existing

Absence is as much a requirement as behaviour, and it is the part that silently survives a rewrite.

| # | What must be absent | How this design makes it absent | How it is verified |
| :---: | :--- | :--- | :--- |
| 1 | The old public route `/api/public/space-event-requests/access/{folio}` | The URL is built once, from `PORTAL_INTEGRATION_PATH_TEMPLATE = "/api/integrations/bloque-hub/leads/{folio}/access"`. There is no second builder and no fallback branch — RN-002 forbids falling back to the public route on `401`, and the code has nowhere to fall back *to* | Repo-wide grep for `space-event-requests` returns zero hits in `src/` and in `portal-mock.py`. The double no longer serves that prefix, so any surviving caller gets a hard `404` |
| 2 | `PORTAL_API_KEY` and the `X-Api-Key` header | `settings.PORTAL_API_KEY` is **deleted** from `config.py` (not defaulted to `None`), and `_build_headers()` is deleted from `client.py` — headers now come exclusively from `PortalHmacAuth` | Grep for `PORTAL_API_KEY` and `X-Api-Key` returns zero hits across `src/`, `.env.example`, and compose files. Deleting the setting rather than ignoring it means a stale `.env` entry is inert (`extra="ignore"`) and a stale *code* reference fails loudly with `AttributeError` at attribute access. Note the mechanism precisely: importing `app.core.config` still succeeds — only D9's missing-credential case fails at import time, with `ValidationError`. Both are loud; they are not the same failure |
| 3 | `data.status_label` in any render path | The client logs it and **never puts it in `PortalGateResult`**. It is absent from `LeadPrefill`, from `FolioValidateResponse`, and therefore from every API response — so no frontend component can render what it cannot receive (RN-010) | Test: `status_label` is not a key of any gate response body. Grep for `status_label` returns hits only in `client.py` (the log call) and `portal-mock.py` |
| 4 | Credential defaults in the repository | D9: annotated, no default. There is no literal to leak and no `\| None = None` to mistake for "optional" | Test: constructing `Settings` with the pair removed from the environment raises `ValidationError`. Grep confirms no key/secret literal in `src/` (the compose-override dev values are the single, commented, intentional exception per §8) |
| 5 | The assumed-contract mock | `portal-mock.py` is rewritten in place: root `status`, the public prefix, and the unauthenticated path all disappear from the file | Sending an unsigned request to the double returns `401 MISSING_CREDENTIALS`; a wrong signature returns `401 INVALID_SIGNATURE` — the two explicit DoD checks (§11) |
| 6 | Tests asserting the old contract | `test_portal_gate_client.py` old cases are **deleted** in the same commit that adds their replacements, not left skipped | No test references root-level `status` or the public route |

---

## 11. File changes

| File | Action | Description |
| :--- | :--- | :--- |
| `src/backend/app/modules/portal_gate/signing.py` | Create | Pure canonical string, HMAC, timestamp, `path_without_query` |
| `src/backend/app/modules/portal_gate/auth.py` | Create | `PortalHmacAuth(httpx.Auth)`, `requires_response_body = True`, RN-012 re-fire |
| `src/backend/app/modules/portal_gate/prefill.py` | Create | `LeadPrefill`, `map_lead_prefill`, `_truncate`, `_masked_folio` |
| `src/backend/app/modules/portal_gate/client.py` | Rewrite | Integration route, `data.status`, `error_code` taxonomy, `INTEGRATION_AUTH_FAILURE`, `429`, log markers, `PortalGateResult` |
| `src/backend/app/api/portal_gate_http.py` | Create | `raise_for_portal_status` + exhaustive `_STATUS_TO_ERROR`. **Slice B2, not C** — see §13 |
| `src/backend/app/core/limits.py` | Create | `REQUERIMIENTOS_ESPECIALES_MAX_LENGTH` (D5) |
| `src/backend/app/core/config.py` | Modify | Add the required pair; **delete** `PORTAL_API_KEY` |
| `src/backend/app/modules/crm/schemas.py` | Modify | `:193` reads the shared constant |
| `src/backend/app/api/public.py` | Modify | **B2:** both call sites switch to `raise_for_portal_status`, catch-all deleted. **C:** `lead_prefill` on `FolioValidateResponse` |
| `src/backend/tests/conftest.py` | Modify | `os.environ.setdefault` for the credential pair |
| `src/backend/tests/test_portal_gate_signing.py` | Create | Known vector, query split, timestamp shape |
| `src/backend/tests/test_portal_gate_auth.py` | Create | Signed-vs-wire path, re-fire, `requires_response_body` |
| `src/backend/tests/test_portal_gate_prefill.py` | Create | Mapping, truncation boundary, degradation |
| `src/backend/tests/test_portal_gate_client.py` | Rewrite | Real contract, taxonomy, retry counts, markers |
| `src/backend/tests/test_portal_mock.py` | Create | Drives the double in-process for the two DoD negative checks |
| `src/backend/tests/test_public_quote_gate.py` | Modify | New coverage + `PortalGateResult` repair — **5 patch sites** (D6) |
| `src/backend/tests/test_public_quote_submit.py` | Modify | New coverage + repair — **6 patch sites** (D6) |
| `src/backend/tests/test_public_rate_limit.py` | Modify | Repair only — **5 patch sites**, incl. `lambda f: PortalFolioStatus.ELIGIBLE` at `:36` (D6) |
| `src/backend/tests/test_public_quote_email.py` | Modify | Repair only — **1 patch site**, `lambda f: PortalFolioStatus.ELIGIBLE` at `:112` (D6) |
| `src/frontend/features/quote-wizard/gate-error.ts` | Create | `readGateError`, `resolveGateFailure` |
| `src/frontend/features/quote-wizard/store/quote-wizard.store.ts` | Modify | `GATE_STATUS` const object, new fields, `hydrateFromPrefill` |
| `src/frontend/app/(public-wizard)/solicitud/page.tsx` | Modify | `reason` branching, hydration, `:60-61` defect fix |
| `src/frontend/features/quote-wizard/components/StepEspacio.tsx` | Modify | Reference-only display block |
| `portal-mock.py` | Rewrite | Real contract + HMAC verification |
| `docker-compose.override.yml` | Modify | Credential pair on both services |

---

## 12. Testing strategy and strict-TDD sequencing

Runner: `pytest` (backend), `playwright` (frontend e2e). **The frontend has no unit runner** —
`package.json` exposes only `test:e2e`. `resolveGateFailure` is therefore covered through Playwright
using `page.route(...)` to stub the API with each status/`reason` pair. Adding vitest is scope creep
and is not proposed; keeping the helper pure keeps that door open.

| Slice | Red → green order | Notes |
| :---: | :--- | :--- |
| **A** | known vector → `signing.py`; query split → `path_without_query`; signed-vs-wire (`MockTransport`, bare `httpx.Client`, no `client.py`) → `PortalHmacAuth`; re-fire fires exactly once **and** `requires_response_body` asserted literally; `Settings` raises without credentials → config change + `conftest` env | Exploits proposal §5.1: every A test lives below the client, so nothing in `public.py` moves |
| **E** | Negative-first: unsigned → `401 MISSING_CREDENTIALS`, bad signature → `401 INVALID_SIGNATURE`, then the `200` envelope | Load the double via `importlib.util.spec_from_file_location` — `portal-mock.py` has a hyphen and is not importable by name. Test only the handler's decisions, never the backend's `signing.py` |
| **B1** | `200` real envelope → ELIGIBLE; route assertion; three headers present; `200` without `data.status` → UNAVAILABLE + `portal_gate.contract_violation` | Delete the old-contract tests in the same commit as their replacements. **Closes RISK-4** |
| **B2** | Parametrized over the §4.5 table, one param per row; request-count assertions (`MISSING_CREDENTIALS` → 1, `TIMESTAMP_EXPIRED` → 2, `429`/`5xx` → N); `caplog` marker tests incl. the RN-018 forbidden-field assertions (§4.1); grep-style absence checks of §10 rows 1-2. **Then, in the same slice:** `test_every_portal_status_is_mapped` → `portal_gate_http.py`; `502` + `reason` on the gate → both `public.py` call sites switch to `raise_for_portal_status` and the `!= ELIGIBLE` catch-all is deleted; the 17-site `PortalGateResult` repair across four test files (D6) | **Enlarged deliberately — see §13.** The enum member and the mapping that handles it are one atomic unit. The slice most likely to blow the review budget; if it must be split, split by `error_code` group and keep the enum + mapping together in whichever sub-slice carries the enum |
| **C** | Pure `prefill.py` tests first (mapping, all-`null`, truncation boundaries, `prefill_truncated` logs length only); then `lead_prefill` present on success and **absent** on every error path | Now purely additive on the API surface: `raise_for_portal_status` already exists and both call sites already use it |
| **D** | Store tests are not available (no unit runner) → Playwright scenarios: auth-failure copy visible with no retry CTA; unknown error does **not** render the folio-rejection copy; success → Step 3 pre-filled and editable; Step 2 shows the reference block with no date preselected | The unknown-error scenario is the regression test for the `:60-61` defect |

---

## 13. Migration / rollout

### 13.1 The one ordering constraint that is not negotiable

**`INTEGRATION_AUTH_FAILURE` and `raise_for_portal_status` must merge in the same PR.**

The proposal's slice sketch puts the enum member in B2 (`client.py`) and the mapping helper in C
(`public.py`). That ordering ships the exact bug this change exists to prevent:

```
B2 merged, C not yet merged
  Portal returns 401 UNKNOWN_API_KEY
    → client.py resolves INTEGRATION_AUTH_FAILURE          (B2: the member exists)
    → public.py still runs `if portal_status != ELIGIBLE:` (C: not merged)
    → 403 FOLIO_NOT_ELIGIBLE
    → the applicant is told their folio is not enabled
```

That is proposal Risk #2, the RN-016 trap of proposal §3, and a direct RN-011 violation — live, in
the deployment window of the change whose entire purpose is to prevent it. It arrives through a
catch-all `else` rather than through a decision, which is precisely the failure shape §3 named.

**Resolution: the mapping helper and both `public.py` call-site switches move from slice C into
slice B2.** A new state and the code that maps it are one unit of correctness and must not be
separable by a merge. This enlarges B2 — already the slice most at risk of exceeding the review
budget — and that cost is accepted, because the alternative is a correctness regression rather than
a review-comfort regression.

If B2 must be split for review size, the split is by `error_code` group. The enum member and
`_STATUS_TO_ERROR` stay together in whichever sub-slice introduces the member; they are never on
opposite sides of a merge boundary.

**Scope note.** The user's decision that B1 ships as an independent release covers **B1 only**. It
does not authorize deploying B2 without its mapping.

### 13.2 Everything else

No data migration. Configuration migration only: every environment must gain the credential pair
**before** the backend restarts, because D9 makes a missing pair a startup failure. That is the
intended trade — a loud refusal to boot instead of a quiet 500 on the first applicant. Local
development is never broken between merges because slice E lands the double before slice B1 changes
the route (proposal §5.2).

Rollback per slice: A, E and B1 are independently revertible. B2 must be reverted as a whole —
reverting only `portal_gate_http.py` while leaving the enum member in place recreates the exact
window described in §13.1.

---

## 14. Open questions

- [ ] **Edge proxy `proxy_intercept_errors` (risk #1).** Not verifiable from this repository. If it
      cannot be confirmed before **slice B2** ships (the slice that now introduces the `502`), flip
      `PORTAL_AUTH_FAILURE_HTTP_STATUS` to `503` and flip the matching row of the frontend fallback
      table — two lines, no logic change (§5). **Still open at archive time (2026-07-28) — see
      WARNING-1 in the archive report.**
- [ ] **Truncation marker wording.** `"… [texto recortado]"` is a placeholder; confirm the exact copy
      (proposal §7.1 asked and got no correction). **Resolved by default: no correction was ever
      received, so the placeholder shipped as the frozen value (tasks.md 0.1).**
- [ ] **Frontend unit runner.** Playwright-only coverage for `resolveGateFailure` works but is slower
      and coarser than a unit test. Flagged, not proposed.
