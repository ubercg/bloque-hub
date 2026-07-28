
# Tasks: Real BLOQUE Portal Integration — Definitive Contract and HMAC Signing (`req-013-portal-hmac`)

**Source:** REQ-013, `proposal.md`, `design.md`, three spec files (`portal-gate-integration`, `quote-gate-api`, `quote-wizard-frontend`).
**Delivery strategy:** `ask-on-risk` — the slicing question is already resolved below (see Review Workload Forecast); no further ask needed before `sdd-apply` starts.
**Chain strategy:** `feature-branch-chain` (tracker branch) — **USER CONFIRMED**. Only the tracker branch ever merges to `main`.
**Strict TDD:** true. Every implementation task below is paired with the test task that must go red before it goes green, in the **same commit** (work-unit-commits skill). `pytest` for backend, `playwright` for frontend (the frontend has no unit runner — `package.json` only exposes `test:e2e`, design §12).

**Locked decisions reflected here (do not re-litigate):**
1. **B1 ships as an independent release** — closes RISK-4 alone, before the error taxonomy exists.
2. **B2 is enlarged and atomic** — `INTEGRATION_AUTH_FAILURE` enum member + `portal_gate_http.py` mapping + **both** `public.py` call-site switches land in the **same commit inside the same slice** (design §13.1). Never separable by a merge boundary. If B2 must split for size, split by `error_code` group only, keeping the enum + `_STATUS_TO_ERROR` together in whichever sub-slice introduces the member.
3. **Truncation marker** for over-long `comentarios`: a **visible marker**, never a silent cut or a drop (D3). Exact copy frozen as design's placeholder pending confirmation — see Phase 0.1.
4. **Auth-failure copy**: system fault, **no call to action** — no "intenta de nuevo", no support contact (D1, frozen verbatim in design §7).
5. **`ciudad` from `lead_prefill`**: ignored entirely — no store field, no display (§4.6, proposal §7.3).
6. **Chain strategy**: `feature-branch-chain` — a draft/no-merge tracker branch accumulates all seven child PRs in dependency order; PR #1 targets the tracker; every later PR targets its immediate predecessor's branch; **only the tracker merges to `main`**. Rationale (design §13.1): if B2 goes wrong, one revert against `main` closes it — not a chase across several already-merged PRs.

Each phase below is one reviewable work unit and one PR. Tests ship in the same commit as the behavior they verify — never split into a separate "tests" commit.

---

## Branch naming

| Branch | Role |
| :--- | :--- |
| `feat/req013-portal-hmac` | **Tracker** — draft, no-merge, opened against `main`. Collects PR #1–#7 in order. Only this branch merges to `main`. |
| `feat/req013-01-signing-auth` | PR #1 (Slice A) — targets the tracker |
| `feat/req013-02-portal-mock` | PR #2 (Slice E) — targets `feat/req013-01-signing-auth` |
| `feat/req013-03-client-happy-path` | PR #3 (Slice B1) — targets `feat/req013-02-portal-mock` |
| `feat/req013-04-error-taxonomy-mapping` | PR #4 (Slice B2, **atomic**) — targets `feat/req013-03-client-happy-path` |
| `feat/req013-05-lead-prefill` | PR #5 (Slice C) — targets `feat/req013-04-error-taxonomy-mapping` |
| `feat/req013-06-frontend-error-states` | PR #6 (Slice D) — targets `feat/req013-05-lead-prefill` |
| `feat/req013-07-rollout-hygiene-docs` | PR #7 (Slice F) — targets `feat/req013-06-frontend-error-states`, last child |

Dependency diagram (current position marked with 📍 once `sdd-apply` starts):

```
Tracker: feat/req013-portal-hmac (draft, no-merge, → main only at the end)
  │
  └─→ PR #1  feat/req013-01-signing-auth              (Slice A)   ✅ done
        │
        └─→ PR #2  feat/req013-02-portal-mock          (Slice E)   ✅ done
              │
              └─→ PR #3  feat/req013-03-client-happy-path      (Slice B1 — closes RISK-4)   ✅ done
                    │
                    └─→ PR #4  feat/req013-04-error-taxonomy-mapping  (Slice B2 — ATOMIC)   ✅ done 📍
                          │
                          └─→ PR #5  feat/req013-05-lead-prefill       (Slice C)
                                │
                                └─→ PR #6  feat/req013-06-frontend-error-states (Slice D)
                                      │
                                      └─→ PR #7  feat/req013-07-rollout-hygiene-docs (Slice F)
                                            │
                                            └─→ tracker merges to main
```

---

## Phase 0 — Confirmations (blocking only where noted, do first)

- [ ] 0.1 **Truncation marker copy.** Freeze `TRUNCATION_MARKER = "… [texto recortado]"` (design §6) as the working value — proposal §7.1 asked and got no correction, so this is not blocking. If product corrects it before Phase 5 (Slice C) starts, the blast radius is exactly one constant in `prefill.py` plus its literal in `test_portal_gate_prefill.py`.
- [ ] 0.2 **Edge-proxy `proxy_intercept_errors` verification (design risk #1, open question §14).** Not verifiable from this repository — the shared edge proxy lives outside it. Must be confirmed **before slice B2 (PR #4) ships**, because B2 is what introduces the `502`. If it cannot be confirmed in time, apply the D1 fallback **inside PR #4 itself**: flip `PORTAL_AUTH_FAILURE_HTTP_STATUS` to `503` and flip the matching `502 → auth_failure` / `503 → unavailable` rows in the frontend fallback table (design §5, §7) — a 2-line change, not a blocker.
- [ ] 0.3 *(informational, already resolved, no action)* Auth-failure copy is frozen verbatim from design §7 (delivery decision #4). Do not alter its "no call to action" property when implementing Phase 6.
- [ ] 0.4 *(informational, already resolved, no action)* `ciudad` is ignored entirely (delivery decision #5). Enforced by task 5.9's negative test — not a fresh decision.

*Blocks: 0.2 gates PR #4's merge readiness only (fallback available); 0.1 gates nothing (default is safe to ship and cheap to correct).*

---

## Phase 1 — Slice A: Signing + auth foundation (PR #1)

**Closes:** nothing on its own (pure/transport layer, no `client.py` change yet) — but unblocks everything downstream, including B1's real HMAC calls.

- [x] 1.1 TDD: `test_portal_gate_signing.py::test_known_vector` — compute the expected Base64 literal with a **standalone `python -c` one-liner from REQ-013 §4.3**, never from the implementation (design's explicit gotcha: a vector generated from the code under test only proves the code equals itself). → implement `signing.canonical_string()` + `signing.sign()`.
- [x] 1.2 TDD: `test_timestamp_is_digits_only_utc_seconds` (RN-005, injectable `now`) → implement `signing.current_timestamp(now: Callable = time.time)`.
- [x] 1.3 TDD: `test_path_without_query_strips_query_string` (RN-004 — a no-op today because the endpoint is a parameterless `GET`, but tested now so it is never silently reintroduced) → implement `signing.path_without_query(raw_path: bytes)`.
- [x] 1.4 TDD: `test_auth_declares_requires_response_body` — literal class-attribute assertion, not a behavioral one, because the behavioral re-fire test can pass for the wrong reason if httpx changes its buffering (design §3) → implement `PortalHmacAuth` skeleton with `requires_response_body = True`.
- [x] 1.5 TDD: `test_signed_path_matches_wire_path` — inside a `MockTransport` handler, recompute the signature from the **received** request and assert equality with the received `X-Bloque-Signature` header, using a bare `httpx.Client`, never `client.py` (RN-003 proven, not assumed) → implement `auth_flow()`'s first `yield` + `_apply_signature()`.
- [x] 1.6 TDD: `test_percent_encoded_path_is_signed_as_transmitted` — drives `PortalHmacAuth` directly with an encoding-sensitive URL, deliberately bypassing `validate_folio` since `FOLIO_PATTERN` makes the case unreachable there; keeps RN-003 covered independently of the folio format → confirm `auth_flow` signs from `request.url.raw_path`, never a reconstructed string.
- [x] 1.7 TDD: `test_refire_fires_exactly_once_on_timestamp_expired` — fresh timestamp + fresh signature per RN-006, no attempt counter, no mutable state on the instance (D8) → implement `_is_timestamp_expired()` + the conditional second `yield` in `auth_flow`.
- [x] 1.8 TDD: `test_refire_without_requires_response_body_crashes_loudly` — regression test verified against the installed httpx 0.28.1: dropping the flag makes `response.json()` raise `httpx.ResponseNotRead`, a **loud crash**, not a silently-skipped re-fire. Protects the mandatory flag from a "harmless-looking" removal.
- [x] 1.9 Config: add `PORTAL_HUB_API_KEY: str` / `PORTAL_HUB_API_SECRET: str` to `core/config.py` — **annotated, no default** (D9). TDD: `test_settings_raises_without_credentials` asserts `Settings()` raises `ValidationError` when either is unset.
- [x] 1.10 `tests/conftest.py`: `os.environ.setdefault(...)` for both new vars at the very top, before any `app.*` import — mirrors the existing `DATABASE_URL` pattern (lines 7-11).
- [x] 1.11 `.env.example`: add both keys with dev-double placeholder values.

*Depends on: nothing. Blocks: Phase 2 (shares the canonical-string definition, not the code), Phase 3 (real HTTP calls need `PortalHmacAuth` wired in).*

---

## Phase 2 — Slice E: Test double rewrite (PR #2)

**Why this lands before B1:** the double is not needed for B's tests (those use `MockTransport`), but it is needed so `docker compose up` stays coherent at every merge point — the moment B1 changes the route, the old mock stops answering (proposal §5.2).

- [x] 2.1 Rewrite `portal-mock.py` routing to `^/api/integrations/bloque-hub/leads/(?P<folio>[^/?]+)/access$` (query stripped first). The old public-route prefix and the root-level `status` field disappear from the file entirely (§10 row 5) — no dual support, no transition period.
- [x] 2.2 Implement the verification order from design §8, **credential checks before folio lookup** so an unsigned request cannot learn whether a folio exists: (1) path match → `404 FOLIO_NOT_FOUND`, (2) all three `X-Bloque-*` headers present → `401 MISSING_CREDENTIALS`, (3) `X-Bloque-Api-Key` matches configured key → `401 UNKNOWN_API_KEY`, (4) timestamp is digits-only → `401 MALFORMED_TIMESTAMP`, (5) `abs(now - ts) <= 300` → `401 TIMESTAMP_EXPIRED`, (6) `hmac.compare_digest` → `401 INVALID_SIGNATURE`, (7) folio fixture lookup → `200` / `403 NOT_ELIGIBLE` / `403 TERMINAL` / `404 FOLIO_NOT_FOUND`.
- [x] 2.3 Re-implement the canonical string **independently** (`f"{method}\n{path}\n{timestamp}"`) — a separate re-implementation, never an import of `signing.py`. Both implementations carry the same `REQ-013 §4.3` citation and the same known vector as a comment, so the compose smoke proves the two readings of the contract agree rather than assuming it by construction.
- [x] 2.4 Fixtures: ≥1 eligible folio with a full `lead_prefill`, one with every optional key `null`, one whose `comentarios` exceeds 5000 characters (exercises D3 locally), one `403 TERMINAL`, one `403 NOT_ELIGIBLE`. All fixture folios must satisfy `FOLIO_PATTERN` or the backend never calls out.
- [x] 2.5 TDD, **negative-first** (design §12): `test_unsigned_request_rejected` → `401 MISSING_CREDENTIALS`; `test_bad_signature_rejected` → `401 INVALID_SIGNATURE`; then `test_valid_signature_returns_200_envelope`. Load `portal-mock.py` via `importlib.util.spec_from_file_location` (hyphenated filename, not importable by name). Test only the handler's decisions, never `signing.py`.
- [x] 2.6 `docker-compose.override.yml`: add `PORTAL_HUB_API_KEY` / `PORTAL_HUB_API_SECRET` to **both** the `backend` and `portal-mock` services with matching, obviously-fake dev values, plus a comment stating these are local-double-only credentials and RN-020 forbids reusing them anywhere else.

*Depends on: Phase 1 (shares the canonical-string definition, not its code). Blocks: Phase 3 (local dev needs the double answering the new route before the route changes).*

---

## Phase 3 — Slice B1: Client happy path — CLOSES RISK-4 (PR #3)

**Independently shippable.** This slice alone restores the funnel even before the error taxonomy (B2) exists — the user's confirmed decision that B1 ships as its own release.

- [x] 3.1 Delete the old-contract assumptions in the **same commit** that replaces them (§10 row 6 — no skip-and-leave): remove `PORTAL_STATUS_FIELD`/`PORTAL_ELIGIBLE_STATUS_VALUE` root-status parsing, remove `_build_headers()`/`X-Api-Key`, remove the old `/api/public/space-event-requests/access/{folio}` URL construction.
- [x] 3.2 New route constant `PORTAL_INTEGRATION_PATH_TEMPLATE = "/api/integrations/bloque-hub/leads/{folio}/access"` — one builder, no fallback branch (§10 row 1: RN-002 forbids falling back to the public route on `401`, and this design has nowhere to fall back *to*).
- [x] 3.3 Wire `httpx.Client(auth=PortalHmacAuth(settings.PORTAL_HUB_API_KEY, settings.PORTAL_HUB_API_SECRET))` into the request loop — every call, including the happy path, is now signed.
- [x] 3.4 TDD: `test_eligible_folio_real_envelope` (`200` + `data.status = "quotation_in_progress"` → `ELIGIBLE`); `test_integration_route_is_called` (assert the URL equals the template, never the old public route — regression guard for §10 row 1).
- [x] 3.5 TDD: `test_three_headers_present_on_every_request` (`X-Bloque-Api-Key`/`Timestamp`/`Signature`).
- [x] 3.6 TDD: `test_missing_data_status_is_contract_violation` — a `200` with no `data.status` key resolves to `UNAVAILABLE` (**never** `NOT_ELIGIBLE`, RN-009) and logs `portal_gate.contract_violation` via `_shape_keys()` (top-level keys only, never values).
- [x] 3.7 Delete the old-contract tests in `test_portal_gate_client.py` in this same commit as their replacements (§10 row 6). A `401` in this slice may still fall through to the pre-existing "unexpected status → `PortalUnavailableError`" branch — the full error taxonomy is explicitly out of scope here and lands in B2; this is an accepted interim behavior, not a new regression (it matches the current PR#9-era handling of an unexpected status code).
- [x] 3.8 Full regression: existing timeout/5xx/429 retry-and-backoff logic (`PORTAL_RETRY_ATTEMPTS`, clamped 1–5) preserved unchanged.

*Depends on: Phase 1 (auth wiring), Phase 2 (local double must answer the new route). Blocks: Phase 4.*

---

## Phase 4 — Slice B2: Error taxonomy + `INTEGRATION_AUTH_FAILURE` + exhaustive mapping — ATOMIC (PR #4)

> **Non-negotiable ordering constraint (design §13.1).** The enum member and the mapping helper that handles it, **plus both `public.py` call-site switches**, merge in the **same commit**. Never let `INTEGRATION_AUTH_FAILURE` exist in `client.py` while either `public.py` call site still runs the old `if portal_status != ELIGIBLE:` catch-all — that ordering silently produces `403 FOLIO_NOT_ELIGIBLE` for an auth failure, the exact RN-011 violation this change exists to prevent. Rollback is **whole-slice**: reverting only `portal_gate_http.py` while leaving the enum member in place recreates the same window.

- [x] 4.1 `PortalGateResult` (status + prefill + `error_code`) with `.eligible(prefill=None)` / `.of(status)` classmethod constructors (D6) — **one** function serves gate and submit (RN-016); no second `fetch_lead_prefill`.
- [x] 4.2 `validate_folio(folio) -> PortalGateResult` — return-type change from the bare `PortalFolioStatus` used in B1.
- [x] 4.3 TDD, parametrized over the §4.5 error table, one param per row: 401 variants (`MISSING_CREDENTIALS`/`UNKNOWN_API_KEY`/`INVALID_SIGNATURE`/`MALFORMED_TIMESTAMP`, and `TIMESTAMP_EXPIRED` terminal-after-refire) → `INTEGRATION_AUTH_FAILURE`, no retry; `403 NOT_ELIGIBLE`/`TERMINAL` + `404 FOLIO_NOT_FOUND` → `NOT_ELIGIBLE`, no retry; `429`/`5xx`/timeout → `UNAVAILABLE` via the transport loop.
- [x] 4.4 TDD request-count assertions: `MISSING_CREDENTIALS` → exactly 1 request; `TIMESTAMP_EXPIRED` → exactly 2; `429`/`5xx` → up to `N` per `PORTAL_RETRY_ATTEMPTS` (non-interaction invariants, design §4).
- [x] 4.5 Add `PortalFolioStatus.INTEGRATION_AUTH_FAILURE` enum member.
- [x] 4.6 Log markers (§4.1) with `caplog` tests: `portal_gate.auth_failure` (masked folio, `error_code`, public `api_key`, host, `latency_ms`); extend `portal_gate.contract_violation` coverage from B1. TDD: assert the secret, `X-Bloque-Signature`, and the canonical string appear in **no** emitted record across the whole client suite.
- [x] 4.7 Delete `PORTAL_API_KEY` entirely from `core/config.py` (not defaulted to `None`) — grep-style test confirming zero hits of `PORTAL_API_KEY` / `X-Api-Key` across `src/`, `.env.example`, and compose files (§10 row 2). *(Automated test scoped to `app/` — the only tree the backend container mounts; `.env.example`/compose/root `src/` were swept manually from the host shell and are clean — see BIT-018.)*
- [x] 4.8 Create `api/portal_gate_http.py`: `PORTAL_AUTH_FAILURE_HTTP_STATUS = 502` (the one-line D1 fallback point, see 0.2), `_STATUS_TO_ERROR` mapping dict, `raise_for_portal_status()` — no-op on `ELIGIBLE`, `KeyError` on an unmapped member → `500 PORTAL_STATUS_UNMAPPED` + `portal_gate.unmapped_status` log, **never** a silent `403`.
- [x] 4.9 TDD: `test_every_portal_status_is_mapped` — `set(PortalFolioStatus) == {ELIGIBLE} | set(_STATUS_TO_ERROR)`; adding a member without a mapping turns this suite red (the test-time half of the "fails loudly twice" mechanism).
- [x] 4.10 TDD: `test_unmapped_status_fails_loudly` — the `KeyError` path resolves to `500`, never `403`.
- [x] 4.11 **Same commit as 4.5, 4.8–4.10:** `public.py:144` and `public.py:545` both switch to `raise_for_portal_status(result.status)`; delete the `if portal_status != ELIGIBLE:` catch-all from **both** sites.
- [x] 4.12 TDD: `502` + `reason = INTEGRATION_AUTH_FAILURE` returned by the gate endpoint on an upstream `401` of any `error_code`.
- [x] 4.13 **D6 repair — 17 patch sites across 4 test files**, all switching a bare `PortalFolioStatus.ELIGIBLE` fake to `PortalGateResult.eligible(...)`/`.of(...)`: `test_public_quote_gate.py` (5 sites), `test_public_quote_submit.py` (6 sites), `test_public_rate_limit.py` (5 sites, incl. the `lambda f: PortalFolioStatus.ELIGIBLE` at `:36`), `test_public_quote_email.py` (1 site, `lambda f: PortalFolioStatus.ELIGIBLE` at `:112`). Full public suite regression re-run green.
- [x] 4.14 Resolve Phase 0.2 (edge-proxy verification) before merging this PR: **this repository's** `nginx.conf` re-confirmed clean (only `proxy_pass` at lines 29, 46, 60, 66, 72, 78 — no `proxy_intercept_errors`/`error_page`) → **kept `502`**. The shared edge proxy in front of this stack lives outside this repository and remains genuinely unverified (not "confirmed safe") — flagged as an open item in BIT-018; the fallback constant (`PORTAL_AUTH_FAILURE_HTTP_STATUS`) is documented as a one-line flip if it's later found to intercept `502`s.

**If B2 must split for review size:** split by `error_code` group (e.g. deterministic-401 group vs. retryable-5xx/429 group), but tasks 4.5 and 4.8–4.11 (enum member, `_STATUS_TO_ERROR`, both `public.py` switches) **must land together** in whichever sub-slice introduces the enum member. Prefer not splitting; if split, merge both sub-slices into the same child branch before opening the next PR downstream — no reviewable unit may ever exist with the enum unmapped.

*Depends on: Phase 3 (extends the B1 client rewrite). Blocks: Phase 5, Phase 6.*

---

## Phase 5 — Slice C: `lead_prefill` mapping + truncation boundary (PR #5)

Purely additive on the API surface now — `raise_for_portal_status` already exists and both call sites already use it.

- [ ] 5.1 `core/limits.py`: `REQUERIMIENTOS_ESPECIALES_MAX_LENGTH = 5000` (D5) — the single source, imported by `prefill.py` **and** `crm/schemas.py:193` (avoids the `crm → portal_gate → crm` import cycle risk).
- [ ] 5.2 `crm/schemas.py:193` reads the shared constant instead of a hard-coded `5000`.
- [ ] 5.3 `prefill.py`: `LeadPrefill` frozen dataclass (11 fields per design §6 — **no `ciudad` field**, delivery decision #5) + `_masked_folio()` helper.
- [ ] 5.4 TDD, pure — no HTTP, per design §12's "pure `prefill.py` tests first": `map_lead_prefill()` complete-prefill case (all fields populated); all-null-keys degrades gracefully with no error and nothing logged as an error (spec: "Prefill hydration tolerates null keys").
- [ ] 5.5 TDD: a malformed/garbage payload degrades to all-`None`s + logs `portal_gate.prefill_degraded` (`_shape_keys()` only) — does **not** change the folio status (RN-013: best-effort, never blocking).
- [ ] 5.6 TDD: `_truncate()` invariant at lengths `limit-1`/`limit`/`limit+1`/`3*limit` — `len(result) <= limit` always; the truncation marker is counted **inside** the budget (delivery decision #3: visible marker, per Phase 0.1's frozen value).
- [ ] 5.7 TDD: `portal_gate.prefill_truncated` log records the folio and `original_length` only — never the text.
- [ ] 5.8 TDD: Portal's `comentarios` key maps **only** to `requerimientos_especiales`; the name `comentarios` does not exist past `prefill.py` (D7, makes RN-021 structural) — assert `descripcion_evento` is untouched by prefill.
- [ ] 5.9 TDD: `ciudad` is never mapped — assert `LeadPrefill` has no `ciudad`-shaped field (delivery decision #5, Phase 0.4).
- [ ] 5.10 API surface: `FolioValidateResponse.lead_prefill: LeadPrefillOut | None` — populated **only** on `ELIGIBLE` for the folio just queried.
- [ ] 5.11 TDD: `lead_prefill` absent from the body on every `422`/`403`/`502`/`503` path (new coverage in both `test_public_quote_gate.py` and `test_public_quote_submit.py`) and absent from every log line.
- [ ] 5.12 TDD: `lead_prefill` never appears on `QuoteRequestSubmitResponse`.

*Depends on: Phase 4 (`raise_for_portal_status` must already exist on both call sites). Blocks: Phase 6.*

---

## Phase 6 — Slice D: Frontend error states + prefill hydration (PR #6)

- [ ] 6.1 `features/quote-wizard/gate-error.ts` (new): `readGateError(err)` + `resolveGateFailure(status?, reason?) -> [GateStatus, string]` — pure, testable without rendering. Must not import from `app/` (a convention, **not enforced** by `.dependency-cruiser.cjs`, which has no rule constraining `features/ → app/` — do not claim tooling coverage that does not exist, design §7).
- [ ] 6.2 `resolveGateFailure` precedence (design §7): `reason` match first (authoritative) → status-code fallback (`422`/`403`/`503`/`502`) → `GATE_STATUS.UNKNOWN_ERROR` + `GENERIC_ERROR_MESSAGE` last, **never** `not_eligible` — this is the fix for the pre-existing `page.tsx:60-61` mislabeling defect.
- [ ] 6.3 Store: `GATE_STATUS` const-object + extracted `GateStatus` type (const-object + extracted-type pattern per the TypeScript skill), adding `AUTH_FAILURE` and `UNKNOWN_ERROR` members.
- [ ] 6.4 Store: new state `leadPrefill`, `fechaTentativa`, `espacioRequerido` + `hydrateFromPrefill(prefill)` bulk action in **one** `set(...)` call. Rules: only non-`null` incoming values are written (a `null` leaves the current value untouched, RN-013, and re-hydration cannot clobber text the applicant already typed); `tipo_evento_sugerido`/`como_conociste_bloque` applied only if the value is a member of the corresponding options constant (a non-member is dropped silently, RN-014 says that is normal); it **never** writes `descripcionEvento` (RN-021 made structural on the frontend too); the three new fields are added to `initialState` so `reset()` clears them.
- [ ] 6.5 `solicitud/page.tsx`: rewrite the branching block at `:49-62` to call `resolveGateFailure(status, detail?.reason)`; on success, `hydrateFromPrefill(data.lead_prefill)` runs **before** `setGateStatus(UNLOCKED)` and `router.push`, so Step 3 mounts already filled.
- [ ] 6.6 `page.tsx`: `AUTH_FAILURE_MESSAGE` copy exactly per design §7 / Phase 0.3 (system fault, no call to action, no claim that an alert was raised — there is no alerting per §2.3).
- [ ] 6.7 `StepEspacio.tsx`: read-only informational `<p>` block rendered when `fechaTentativa` or `espacioRequerido` is non-null — not bound to any input. Explicit prohibition: no effect may feed these into `addItem`, a date default, or a `space_id` lookup (RN-015, RN-022).
- [ ] 6.8 Confirm `StepSolicitante.tsx` needs **no change** — it is already controlled from the same store keys `hydrateFromPrefill` writes. Do not add an effect there.
- [ ] 6.9 Playwright e2e (no unit runner exists, design §12): auth-failure copy visible with no retry CTA and textually distinct from the not-eligible and Portal-unavailable messages; unknown-error scenario does **not** render folio-rejection copy (regression test for the `:60-61` defect); success → Step 3 pre-filled and editable; Step 2 shows the reference block with no date/space preselected; `status_label` never rendered anywhere via `page.route()` stubbing a `status_label` value and asserting its absence from the DOM.

*Depends on: Phase 5 (`lead_prefill` must exist on the wire). Blocks: Phase 7.*

---

## Phase 7 — Slice F: Rollout, secret-hygiene verification, living docs (PR #7 — last child, tracker merge gate)

External Portal-team credential delivery blocks **only** tasks 7.4–7.5 (proposal §5.2); everything else in this phase can start as soon as Phase 6 merges.

- [ ] 7.1 Secret-hygiene check #1 (§9): test asserting `FolioValidateResponse.model_fields` and `LeadPrefillOut.model_fields` contain no key matching `api_key|secret|signature`.
- [ ] 7.2 Secret-hygiene check #2: test asserting the configured secret is not a substring of the serialized body on every gate/submit path, success and error.
- [ ] 7.3 Secret-hygiene check #3 — **the one the DoD actually asks for**: `npm run build` in `src/frontend`, then grep the emitted `.next/static` and `.next/server` output for the secret value and the literals `PORTAL_HUB_API_SECRET` / `PORTAL_HUB_API_KEY` — zero hits required. Run in CI after the build step, or record as a manual release check in the bitácora if CI has no frontend build stage.
- [ ] 7.4 Per-environment credential rollout: staging and production each get a **distinct** `PORTAL_HUB_API_KEY`/`SECRET` pair, never shared (RN-020) — delivered by the Portal team.
- [ ] 7.5 Connected smoke test against the real Portal (or Portal staging) once credentials arrive: one eligible folio unlocks end to end — verifies RISK-4 closure live, not just against the local double.
- [ ] 7.6 Repo-wide grep sweep (final gate before the tracker merges to `main`): zero hits for `space-event-requests`, `PORTAL_API_KEY`, `X-Api-Key`; `status_label` appears only in `client.py`'s log call and `portal-mock.py` (full §10 removals table).
- [ ] 7.7 **Living documentation** (mandatory, `.cursorrules`/`CLAUDE.md`/`AGENTS.md` rule — Obsidian vault, not this repo): rewrite `30-API/API-024-*.md` for the new contract and `lead_prefill`; tick REQ-013 DoD checkboxes in `10-Requerimientos/`; update `20-Arquitectura/ARQ-001-Decisiones-Core.md` with `PORTAL_HUB_API_KEY`/`SECRET`, `REQUERIMIENTOS_ESPECIALES_MAX_LENGTH`, and the retirement of `PORTAL_API_KEY`; close RISK-4 in REQ-012's risk log; new `50-Bitacora/BIT-XXX-Estatus-REQ-013.md` entry with implementation summary, local smoke-test results, and anything still pending (e.g. unresolved 0.2 proxy verification, credential delivery status).

*Depends on: Phase 6 (full frontend flow must exist to smoke-test end to end) + external Portal credentials (blocks 7.4/7.5 only).*

---

## Task → Requirement traceability

| PR | Slice | Spec requirements covered |
| :-- | :-- | :-- |
| #1 | A | *portal-gate-integration*: Credential configuration per environment; Canonical string construction; HMAC signature computation; Fresh signature per attempt; 401 retry policy (re-fire mechanics only — terminal resolution is B2); Secret hygiene (signing happens only in the backend) |
| #2 | E | *portal-gate-integration*: Test double verifies signatures (bad signature → 401, missing headers → 401) |
| #3 | B1 | *portal-gate-integration*: Integration route only; Status parsing from `data.status` (incl. missing-status contract violation); Retirement of the legacy API key (client stops sending `X-Api-Key`) |
| #4 | B2 (atomic) | *portal-gate-integration*: 401 retry policy (terminal resolution to `INTEGRATION_AUTH_FAILURE`); Error-code taxonomy; `status_label` is diagnostic-only; Retirement of the legacy API key (setting deleted); Secret hygiene (log field lists) — *quote-gate-api*: Exhaustive status-to-HTTP mapping — *quote-wizard-frontend*: Portal copy is never displayed (backend half: `status_label` absent from every response) |
| #5 | C | *quote-gate-api*: `lead_prefill` exposure scope; `comentarios` truncation at the prefill boundary; Prefill hydration tolerates null keys (backend half); Field-specific mapping constraints (backend half) |
| #6 | D | *quote-wizard-frontend*: Distinct auth-failure state; Unknown reason fallback; Store hydration from prefill; Portal copy is never displayed (frontend half) — *quote-gate-api*: Prefill hydration tolerates null keys (frontend half); Field-specific mapping constraints (frontend half — reference-only display, editability) |
| #7 | F | Cross-cutting: Secret hygiene (bundle-grep check, the one the DoD literally requires); RISK-4 closure end-to-end |

---

## Review Workload Forecast

**Estimated changed lines (additions + deletions), by PR, grounded against current file sizes** (`client.py` 160 lines, `public.py` 692 lines, `test_public_quote_submit.py` 753 lines, `test_public_quote_gate.py` 105 lines, `test_public_rate_limit.py` 223 lines, `test_public_quote_email.py` 185 lines):

| PR | Slice | Est. changed lines | Notes |
| :-: | :-: | --: | :-- |
| #1 | A | 220–320 | 2 new modules (`signing.py`, `auth.py`) + 2 new test files + config/conftest/`.env.example` diffs |
| #2 | E | 300–450 | Full rewrite of `portal-mock.py` (deletions count too) + new `test_portal_mock.py` + compose diff |
| #3 | B1 | 250–380 | Partial `client.py` rewrite + partial `test_portal_gate_client.py` rewrite (old-contract tests deleted here) |
| #4 | B2 | **550–750** | Finishes `client.py`; new `portal_gate_http.py`; both `public.py` call sites; **17-site D6 repair across 4 test files**, one of which (`test_public_quote_submit.py`) is 753 lines on its own. **Highest risk in this change — see split rule in Phase 4.** |
| #5 | C | 250–350 | New `limits.py` + `prefill.py` + new `test_portal_gate_prefill.py` + additive coverage in 2 integration suites |
| #6 | D | 280–400 | New `gate-error.ts`; store, `page.tsx`, `StepEspacio.tsx` diffs; new Playwright specs |
| #7 | F | 100–180 | Hygiene tests + CI/bitácora wiring; bulk of the phase is Obsidian docs (outside repo diff, not counted) |
| **Total (repo diff)** | | **~1,950–2,830** | Excludes Obsidian living-docs content, which lives outside this repository |

**400-line budget risk: High.** Five of seven PRs individually exceed or approach 400 lines; PR #4 (B2) is very likely to exceed 400 on its own even after the D6 repair is counted honestly against real file sizes rather than the proposal's original estimate.

**Chained PRs recommended: Yes.**

**Decision needed before apply: No** — chain strategy (`feature-branch-chain`, tracker branch) is already confirmed by the user (see Locked decisions #6 above). `sdd-apply` may proceed directly to Phase 0 without a further slicing ask. The only remaining open item is Phase 0.2 (edge-proxy verification), which has a pre-agreed fallback and does not block starting.

**If PR #4 exceeds budget in practice:** apply the Phase 4 split rule (by `error_code` group, enum + mapping never separated by a merge boundary) rather than re-opening the chain-strategy question.
