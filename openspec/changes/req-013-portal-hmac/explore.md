# Exploration — req-013-portal-hmac

**Change:** `req-013-portal-hmac`
**Requirement:** REQ-013 — Real BLOQUE Portal integration: definitive contract and HMAC signing
**Phase:** explore
**Date:** 2026-07-28
**Artifact store:** openspec (mirrored in Engram at `sdd/req-013-portal-hmac/explore`)

> Source of truth for the requirement lives outside this repo, in the Obsidian vault:
> `100-🎯-Proyectos/bloque_hub/10-Requerimientos/REQ-013-Integracion-Real-Portal-Firma-HMAC.md`.
> The §11 decisions in that document are **closed**. Downstream phases must treat RN-010,
> RN-019, RN-020, RN-021 and RN-022 as settled and must not reopen them.

---

## 1. Current state

`portal_gate/client.py` implements the **old assumed contract** end to end:

| Aspect | Location | Current behavior |
| :--- | :--- | :--- |
| Path | `client.py:93` | `GET {PORTAL_API_BASE_URL}/api/public/space-event-requests/access/{folio}` |
| Auth | `client.py:67-71` | Optional `X-Api-Key`, header added only when `settings.PORTAL_API_KEY` is set |
| Status parsing | `client.py:24,74-79` | `PORTAL_STATUS_FIELD = "status"`, read at the **JSON root** via `body.get(...)` |
| Enum | `client.py:48-51` | `ELIGIBLE` / `NOT_ELIGIBLE` / `UNAVAILABLE` only |
| 403 / 404 | `client.py:120-121` | → `NOT_ELIGIBLE`, no retry |
| 5xx / timeout | `client.py:102-141` | Retried up to `PORTAL_RETRY_ATTEMPTS` (clamped 1–5, `client.py:35-41`), then `PortalUnavailableError` |
| Any other status (401, 429) | `client.py:143-154` | Raises `PortalUnavailableError` immediately, **no retry** |

**Confirmed defect (RISK-4).** The real contract nests the status at `data.status`. Reading it at the
root means `body.get("status")` returns `None` for every response, and `_extract_status` falls through
to `return PortalFolioStatus.NOT_ELIGIBLE`. Pointed at the real Portal, **every eligible folio is
rejected**.

**Correction carried from the requirement.** A 401 does *not* currently surface to the applicant as
"folio not enabled": `client.py:143-154` raises `PortalUnavailableError`, which `public.py:145`
handles in a branch separate from the `NOT_ELIGIBLE` branch at `public.py:151`, producing
`503 PORTAL_UNAVAILABLE`. The new `INTEGRATION_AUTH_FAILURE` state is justified by **retry semantics**
(RN-012) and **operator diagnostics** (HU-05), not by fixing a user-facing defect.

---

## 2. Blast radius

| File | What changes |
| :--- | :--- |
| `src/backend/app/modules/portal_gate/client.py` | Full rewrite: path, HMAC signing, `data.status` parsing, `error_code` mapping, new state, RN-012 retry policy |
| `src/backend/app/core/config.py:82-87` | Retire `PORTAL_API_KEY`; add required `PORTAL_HUB_API_KEY` / `PORTAL_HUB_API_SECRET` with no defaults |
| `src/backend/app/api/public.py:108-112` | `FolioValidateResponse` grows `lead_prefill` |
| `src/backend/app/api/public.py:144,545` | Gate and submit revalidation — already share one function, keep it that way |
| `src/frontend/app/(public-wizard)/solicitud/page.tsx:18-62` | Third error branch for `INTEGRATION_AUTH_FAILURE`; prefill handoff |
| `src/frontend/features/quote-wizard/store/quote-wizard.store.ts` | New bulk-hydrate action for Step 3 |
| `portal-mock.py` + `docker-compose.override.yml` | Full rewrite with real HMAC verification (RN-019) |
| `src/backend/tests/test_portal_gate_client.py` | Full rewrite — every test asserts the old contract |

`PORTAL_BASE_URL` (display link) is **distinct** from `PORTAL_API_BASE_URL` (API host). Do not conflate
them during the config change.

---

## 3. The gate → frontend data path

`page.tsx:45` posts `{folio}` to `/public/quote-requests/validate-folio` → `public.py:144` calls
`validate_folio` → maps to 200 / 403 / 503 → the frontend switches on the **HTTP status code** at
`page.tsx:49-62` and writes `gateStatus` into the Zustand store (`quote-wizard.store.ts:26,141-146`).

`lead_prefill` has **zero references anywhere in the repository** (repo-wide grep). Threading it
requires three coordinated changes:

1. `FolioValidateResponse` grows a `lead_prefill` object.
2. The wizard store gets a hydrate action mapping the 12 contract keys of REQ-013 §4.6.
3. `page.tsx` calls that action after a successful gate response.

Step 3 fields today are set individually through `setField` in `StepSolicitante.tsx`; there is no bulk
hydrate action to extend.

---

## 4. Submit revalidation path (RN-016)

`public.py:144` (gate) and `public.py:545` (submit revalidation) both call the identical
`portal_gate_client.validate_folio(folio)` with identical exception handling. **RN-016 is already
satisfied structurally** — there is no duplicated path to unify. The requirement is to *keep* this
true after the rewrite, not to create it.

---

## 5. Test surface

| Test file | Impact |
| :--- | :--- |
| `test_portal_gate_client.py` | **Full rewrite.** All 15+ tests assert the old contract (root `status`, no auth headers, old path) |
| `test_public_quote_gate.py` | Unaffected by the rewrite; needs *new* coverage for `INTEGRATION_AUTH_FAILURE` and `lead_prefill` |
| `test_public_quote_submit.py` | Same as above |
| `test_public_rate_limit.py` | Unaffected |
| `test_public_quote_email.py` | Unaffected |

**Why the split matters for strict TDD.** `test_portal_gate_client.py` fakes Portal at the *HTTP*
layer — it monkeypatches the `httpx.Client` constructor to inject an `httpx.MockTransport`
(`_patch_client`, lines 21-42). The `public.py` integration tests fake Portal at the *function*
boundary — they monkeypatch `public_module.portal_gate_client.validate_folio` directly and never touch
HTTP. Consequently `client.py` can be driven red-green in isolation without disturbing the integration
suite. New HMAC known-vector tests plug into the existing `MockTransport` seam.

**httpx version:** `httpx>=0.27.0` (`requirements.txt:4`) — supports the generator-based
`httpx.Auth.auth_flow(request)`.

---

## 6. Config and secrets

Settings load through `pydantic_settings.BaseSettings` reading `.env` (`config.py:6-11`).

**No secret reaches the frontend bundle today.** Grepping `PORTAL_HUB` / `PORTAL_API_KEY` / `X-Api-Key`
across `src/` hits only `client.py` and `config.py`; frontend `NEXT_PUBLIC_` hits are unrelated
(`auth-middleware.ts`, `apiClient.ts`, `next.config.ts`, catalog/admin/scanner code). The RN-017 work is
to **keep this closed**, not to close it.

---

## 7. Signing layer — approach comparison

RN-003's crux: the signed `PATH` must be byte-identical to what actually travels on the wire.

| # | Approach | Pros | Cons | Effort |
| :---: | :--- | :--- | :--- | :---: |
| 1 | Inline signing inside `validate_folio` | Minimal diff, no new abstraction | Signed path computed independently of what httpx sends; safe today only because folios are alphanumeric + hyphen. Poor isolated testability. RN-012's one-shot re-fire must be hand-rolled into the already dense 5xx/timeout loop | Low |
| 2 | `httpx.Auth` subclass (`auth_flow` generator) | `auth_flow(request)` receives the fully normalized `httpx.Request`; `request.url.raw_path` is byte-identical to the wire path — directly satisfies RN-003. The two-step yield/receive/re-yield protocol is a natural home for RN-012's single re-fire | Couples signing to httpx's Auth protocol. Creates a second retry mechanism alongside the existing loop, whose interaction must be defined | Medium |
| 3 | Separate `signing.py` with pure functions | Highly unit-testable against the DoD's fixed known-vector test, independent of any HTTP client | Still needs wiring to guarantee byte-identity with the wire path | Low–Med |

**Recommendation for the design phase (not decided here):** combine **2 + 3**. Pure `signing.py` for the
canonical-string and HMAC math, wired through an `httpx.Auth` subclass — or `client.build_request()`
followed by an explicit `raw_path` read — so the signed path is provably identical to what httpx
transmits, and RN-012's single re-fire lives in `auth_flow` rather than tangled into the retry loop.

**Note on current safety:** `FOLIO_PATTERN` (`client.py:28`) restricts folios to digits and hyphens, so
no percent-encoding-sensitive characters occur today. The byte-identity risk is currently inert, but the
design must not depend on that remaining true.

---

## 8. Risks and unknowns not anticipated by REQ-013

1. **The frontend cannot distinguish a third error state today.** `page.tsx:49-62` branches purely on
   HTTP status code and never reads `detail.reason` from the body. Surfacing `INTEGRATION_AUTH_FAILURE`
   requires a real design decision — a new distinct HTTP status, or a refactor to branch on
   `detail.reason` — not merely a new enum value.

2. **The frontend already mislabels unknown errors as folio rejection.** `page.tsx:60-61`: the final
   `else` sets `setGateStatus('not_eligible', GENERIC_ERROR_MESSAGE)`. A network failure or an
   unexpected 500 is therefore recorded in the store as `not_eligible`. This is the same
   category confusion RN-011 forbids, on the frontend side, and it exists **independently** of this
   change. The design phase should decide whether to fix it here or carve it out explicitly.

3. **`requerimientos_especiales` has a 5000-character cap** (`schemas.py:193`) with no word-count rule.
   A very long `comentarios` from Portal could still hit the character cap. REQ-013's DoD exercises the
   300-word case (the RN-021 motivation) but not the character cap.

4. **Two independent retry mechanisms.** The existing timeout/5xx loop and RN-012's single re-fire on
   `TIMESTAMP_EXPIRED` are triggered independently. Precedence is undefined by the requirement: does a
   re-fired-then-still-401 consume a `PORTAL_RETRY_ATTEMPTS` slot?

5. **Log markers are net-new conventions.** No observability infrastructure exists (no Sentry,
   Prometheus, webhooks, or structured logging config). `portal_gate.auth_failure` and
   `portal_gate.contract_violation` establish a convention rather than extending one.

---

## 9. Readiness

**Ready for `sdd-propose`.** Blast radius is enumerated with line anchors, the gate/submit shared path
is confirmed a non-issue, test impact is scoped precisely, and the signing approaches are laid out with
tradeoffs. The four open design decisions above are the ones the proposal must resolve.
