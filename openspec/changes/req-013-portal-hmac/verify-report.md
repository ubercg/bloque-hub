# Verification Report — req-013-portal-hmac

**Change:** `req-013-portal-hmac`
**Mode:** full artifacts (proposal, specs, design, tasks) + REQ-013 §7 DoD (source of truth)
**Date:** 2026-07-28
**Branch inspected:** `feat/req013-07-rollout-hygiene-docs`

## Verdict: PASS WITH WARNINGS — **do not archive yet**

No CRITICAL findings. The implementation matches the spec and design faithfully, including the
highest-risk items called out in the verification brief (known-vector independence, RN-003 byte
identity, `requires_response_body`, the B2 atomicity constraint, and the six §10 absence
requirements). WARNING-2 is **CLOSED** (`e1c0bdf`). Connected Portal smokes (+/−) and local clock
checks ran 2026-07-28; prefill key fidelity was corrected in `e49b23f` after the lying-double
finding (see §3 addendum). Remaining before archive: **WARNING-1 (Sigao edge proxy)** and
**RN-020 second credential pair if staging exists apart from prod**.

---

## 1. Test execution (real, not inferred)

### Backend — pytest, in the running `backend` container (`docker compose exec backend pytest`)

**Full suite** (`tests/`, excluding 5 pre-existing collection errors unrelated to this change —
`test_agenda_phased.py`, `test_contract_cfdi_snapshot.py`, `test_group_booking.py`,
`test_montaje_gating.py`, `test_roadmap_integration.py`, all failing on stale imports from an
unrelated `booking` module refactor):

```
38 failed, 318 passed, 5 skipped, 10 errors in 41.25s
```

All 38 failures + 10 errors are pre-existing `sqlalchemy.exc.ProgrammingError: unrecognized
configuration parameter "app.current_tenant"` / RLS/schema-state failures across
finance/CFDI/UMA/fulfillment/booking — **zero overlap with `portal_gate`, `public.py`
quote-gate/submit, or `portal-mock` tests.** This matches the baseline explicitly recorded in
commit `fe0057c`'s message ("38 unrelated DB/schema-state failures... already present on main").

**REQ-013-scoped files** (`test_portal_gate_signing.py`, `test_portal_gate_auth.py`,
`test_portal_gate_client.py`, `test_portal_gate_prefill.py`, `test_portal_gate_secret_hygiene.py`,
`test_portal_gate_http.py`, `test_portal_mock.py`, `test_public_quote_gate.py`,
`test_public_quote_submit.py`, `test_public_rate_limit.py`, `test_public_quote_email.py`,
`test_config.py`, `test_core_limits.py`):

```
171 passed, 0 failed in 1.98s
```

### Frontend — Playwright (`tests/e2e/solicitud-gate.spec.ts`, REQ-013 Slice D), against the live
docker stack (`nginx` on `localhost:80`, backend + portal-mock live)

First attempt with the default 4 workers produced 4 spurious timeouts on `page.goto` (60s test
timeout exceeded navigating to `/bloque/solicitud`), while the other 5 tests in the same file
passed. Re-ran **serially** (`--workers=1`) to isolate cause:

```
9 passed (23.5s)
```

All 9 tests pass deterministically, including the setup logins. The parallel-run timeouts are a
resource-contention artifact of 4 concurrent cold Next.js/Turbopack compiles against this dev
container, not a code defect — `curl http://localhost/bloque/solicitud` independently returns
`200` in ~0.1–0.15s. See SUGGESTION-1.

---

## 2. Priority findings (per the verification brief, in order)

### 1. Known-vector test independence — VERIFIED, not circular

`test_portal_gate_signing.py::test_known_vector` (`SECRET="test-secret-vector"`, `METHOD="GET"`,
`PATH="/api/integrations/bloque-hub/leads/BCE-20260715-172822-2973/access"`,
`TIMESTAMP="1767225600"`) asserts the literal `cVq1YbWSfBtJ6/9/LrBEwU33gazDGTxcKE3Bi7o3ITA=`.

Recomputed independently, outside pytest and outside `signing.py`, with a standalone `python3 -c`
using stdlib `hmac`/`hashlib`/`base64` directly against REQ-013 §4.3's algorithm:

```
canonical = 'GET\n/api/integrations/bloque-hub/leads/BCE-20260715-172822-2973/access\n1767225600'
signature = cVq1YbWSfBtJ6/9/LrBEwU33gazDGTxcKE3Bi7o3ITA=
```

Matches the literal in the test exactly. The vector is genuinely independent — the test would
catch an accidental separator or encoding change.

### 2. Signed path == wire path, byte for byte (RN-003) — VERIFIED

`auth.py::_apply_signature` reads `request.url.raw_path` (the normalized `httpx.Request`'s bytes)
and `signing.path_without_query()` splits on the first `b"?"` — never a reconstructed string.
`test_signed_path_matches_wire_path` and `test_percent_encoded_path_is_signed_as_transmitted`
both recompute the expected signature from the **received** request inside a `MockTransport`
handler and assert equality against the received `X-Bloque-Signature` header. Both pass.

### 3. `requires_response_body = True` — PRESENT and test-guarded correctly

Confirmed at `auth.py:24`. `test_refire_without_requires_response_body_crashes_loudly`
(`test_portal_gate_auth.py:140`) constructs an unread `SyncByteStream`, subclasses
`PortalHmacAuth` with the flag flipped off, and asserts `httpx.ResponseNotRead` is raised —
exactly the "loud crash, not a silently-skipped re-fire" flaw the design warned test-writers
against getting wrong. It does **not** assert "only one request was sent" (the flawed pattern
design §3 called out). `test_auth_declares_requires_response_body` independently pins the literal
class attribute. Both pass.

### 4. B2/C ordering constraint (design §13.1) — HELD

Commit `fe0057c` ("closes B2") diffstat: `portal_gate_http.py` (created), `client.py`
(`INTEGRATION_AUTH_FAILURE` enum member added), and `public.py` (both call sites switched) —
all in the **same commit**. Grep confirms zero surviving `if portal_status != ELIGIBLE:`
catch-alls; both `public.py:172` and `public.py:566` (current line numbers) call
`raise_for_portal_status(result.status)`. The enum member and its mapping never existed
un-paired at any commit boundary.

### 5. Six absence requirements (design §10) — ALL CLEAN, verified by grep

| # | Item | Result |
|---|---|---|
| 1 | `/api/public/space-event-requests/access/{folio}` | 3 hits total in `src/`, all in tests asserting its **absence** (`test_portal_mock.py:208` — now 404s; `test_portal_gate_client.py:540,571` — asserts not in built URL) |
| 2 | `PORTAL_API_KEY` / `X-Api-Key` | 3 hits, all inside `test_config.py`'s own grep-style regression test; zero in live code, `.env.example` (not independently readable — sandboxed — but `test_config.py` and the Slice-F sweep note in `tasks.md:194` cover it), or compose files |
| 3 | `status_label` in a render path | Hits only in `portal-mock.py` (sending it, as Portal would) and `client.py:147,150` (diagnostic log call); frontend hits are e2e specs stubbing/asserting its **absence** from the DOM |
| 4 | Credential defaults in repo | `config.py:98-99`: `PORTAL_HUB_API_KEY: str` / `PORTAL_HUB_API_SECRET: str`, no default. `test_settings_raises_without_credentials` passes |
| 5 | Assumed-contract mock | `portal-mock.py` routes only `^/api/integrations/bloque-hub/leads/(?P<folio>[^/?]+)/access$`; no root `status` field remains |
| 6 | Old-contract tests skipped vs deleted | Zero `skip`/`xfail` markers found in any of the 6 REQ-013-touched test files — confirmed deleted, not disabled |

### 6. Log hygiene (RN-018, design §4.1) — VERIFIED, structurally enforced

`client.py::_extract_status` (contract-violation path) and `_resolve_auth_failure` (auth-failure
path) both log through `_shape_keys()` / explicit field lists — no `%r` of `body`, no
`json.dumps(body)`. `auth.py` contains **zero** logging calls of any kind (the layer that touches
the secret never logs). `test_portal_gate_client.py` has a **module-wide `autouse` fixture**
(`_no_secret_leak_in_any_log`, line 34) that asserts, after every single test in the file
(171 assertions across the suite, not just failure-path tests), that `settings.PORTAL_HUB_API_SECRET`,
the literal `X-Bloque-Signature`, and the canonical string's `"GET\n"` prefix never appear in any
captured log record. This is the strongest form of the check available and it passes.

### 7. Task 0.2 — edge-proxy blocker: current state, explicitly

- **Constant:** `PORTAL_AUTH_FAILURE_HTTP_STATUS = status.HTTP_502_BAD_GATEWAY` (`portal_gate_http.py:35`) — **unchanged**, D1 fallback was **not** applied.
- **This repo's `infra/nginx/nginx.conf`:** re-verified directly — zero hits for `proxy_intercept_errors` or `error_page`. A `502` passes through this repo's nginx unmodified. This matches task 4.14's claim exactly.
- **Frontend fallback table (`gate-error.ts:65-81`):** consistent with the 502 constant — `case 502: → AUTH_FAILURE`, `case 503: → UNAVAILABLE`, with an explicit code comment cross-referencing the backend constant so a future flip is visible from both ends.
- **Task 0.2 checkbox:** correctly left unchecked in `tasks.md` — it was never claimed resolved. The **shared edge proxy outside this repository remains genuinely unverified**, and B2 (which introduces the 502) has already shipped and merged into the tracker.
- **Assessment:** this is accurately self-reported, not a hidden gap. But it is a live, unresolved production risk exactly as tasks.md 0.2 states: if the external shared edge proxy intercepts `502` responses (a common default for reverse proxies fronting upstream error pages), the frontend never sees `detail.reason: INTEGRATION_AUTH_FAILURE` and `resolveGateFailure`'s status-code fallback for `502` never fires either — the applicant would see whatever the intercepting proxy renders, not Hub's own auth-failure copy. See WARNING-1.

---

## 3. Full DoD sweep (REQ-013 §7)

All items below cite `file:line` or test name as evidence, independent of the DoD's own citations.

### Cliente y firma
| Criterion | Status | Evidence |
|---|---|---|
| Integration route only, old route unreachable | **MET** | `client.py:29` `PORTAL_INTEGRATION_PATH_TEMPLATE`; absence confirmed §2.5 above |
| 3 headers on every request | **MET** | `test_three_headers_present_on_every_request`, `test_headers_present_on_a_retried_request_too` — pass |
| Canonical string exact, signature formula | **MET** | `signing.py:23-33`; known vector §2.1 |
| Signed path byte-identical to wire path | **MET** | §2.2 above |
| Timestamp UTC seconds, digits-only | **MET** | `test_timestamp_is_digits_only_utc_seconds` — pass |
| Fresh timestamp+signature per retry | **MET** | `test_refire_fires_exactly_once_on_timestamp_expired` asserts both differ — pass |
| `PORTAL_API_KEY`/`X-Api-Key` retired | **MET** | §2.5 row 2 |
| `PORTAL_HUB_API_KEY`/`SECRET` no repo defaults | **MET** | `config.py:98-99` |

### Parseo del contrato
| Criterion | Status | Evidence |
|---|---|---|
| Eligibility from `data.status`, `PORTAL_STATUS_FIELD` gone | **MET** | grep confirms zero hits; `client.py:33,160` |
| Missing `data.status` → `UNAVAILABLE`, never `NOT_ELIGIBLE` | **MET** | `test_missing_data_status_is_contract_violation`, `test_missing_data_key_entirely_is_contract_violation` — pass |
| `status_label` diagnostic-only, never rendered | **MET** | §2.5 row 3 |
| Mapping by `error_code`, no `message` parsing | **MET** | `_extract_error_code` reads `error_code` only (`client.py:129-136`); grep for `body.get("message"` / `body\["message"\]` in `portal_gate/` returns nothing |
| Contract-violation log records keys only | **MET** | `test_missing_data_status_logs_contract_violation_with_keys_only` — pass |

### Estados y experiencia
| Criterion | Status | Evidence |
|---|---|---|
| `INTEGRATION_AUTH_FAILURE` distinct member | **MET** | `client.py:67` |
| Five 401 variants → `INTEGRATION_AUTH_FAILURE`, none → `NOT_ELIGIBLE` | **MET** | `TestValidateFolioAuthFailureTaxonomy` parametrized — pass |
| Retry counts: deterministic 401s → 1, `TIMESTAMP_EXPIRED` → 2 | **MET** | `test_timestamp_expired_refire_costs_exactly_two_requests` etc. — pass |
| UI shows non-retryable system-fault copy for auth failure, distinct from not-eligible/unavailable | **MET** | e2e `falla de autenticación...` + `...son textualmente distintos` — pass (serial run) |
| 403/404 variants → `NOT_ELIGIBLE`, no retry | **MET** | `TestValidateFolioNotEligibleTaxonomy` — pass |

### Prefill del Paso 3
| Criterion | Status | Evidence |
|---|---|---|
| `lead_prefill` returned on success, Step 3 hydrated | **MET** | backend: `test_eligible_with_prefill_populates_every_field`; frontend e2e `el gate exitoso hidrata...` — pass |
| All prefilled fields editable | **MET** | e2e edits `Nombre completo` post-hydration and confirms new value — pass |
| Null keys don't error/block, incl. `tipo_evento_sugerido = null` | **MET** | `test_all_null_keys_degrade_gracefully_with_no_error_log` — pass |
| `espacio_requerido` never resolves `space_id` | **MET** | `StepEspacio.tsx` read-only block, no `addItem` binding; e2e asserts `aria-pressed=false`, no bandeja — pass |
| `comentarios` → `requerimientos_especiales` only, never `descripcion_evento` | **MET** | D7 structural — `LeadPrefill` has no `comentarios` field (`test_has_no_comentarios_field`); `test_comentarios_lands_only_on_requerimientos_especiales` — pass |
| `comentarios` > 300 words doesn't break submit | **MET** (WARNING-2 closed) | Explicit test: `test_comentarios_over_300_words_survives_prefill_without_word_cap` — 301 words via `map_lead_prefill` → `requerimientos_especiales`; same text fails RN-006 on `descripcion_evento`, passes on `requerimientos_especiales`. Commit `e1c0bdf`. Char-cap truncation coverage remains in `TestTruncationBoundary`. |
| `fecha_tentativa` reference-only, no Step 2 preselection | **MET** | e2e `Step 2 muestra el bloque de referencia...` asserts no bandeja item exists — pass |
| `lead_prefill` never on error/submit responses | **MET** | `test_invalid_format_never_returns_lead_prefill`, `test_not_eligible_never_returns_lead_prefill`, `test_portal_unavailable_never_returns_lead_prefill`, `test_auth_failure_never_returns_lead_prefill`, `test_lead_prefill_never_appears_on_the_submit_response` — all pass |

> **Addendum 2026-07-28 (post-verify, after connected smoke) — re-evidence Prefill rows.**
>
> The Prefill criteria above were marked **MET** during the original verify pass on the strength
> of green unit/e2e tests against `portal-mock.py`. That evidence was **not valid for production
> hydration**: the double emitted obsolete key names (`nombre_solicitante` / `email_solicitante` /
> `telefono_solicitante` / `numero_invitados`) that Portal real does not send, while Portal real
> sends Hub-canonical keys plus English synonyms in the same object (REQ-013 §4.6, verified on
> folio `BCE-20260717-121058-4083`). RN-019 had been read as “HMAC fidelity”; payload key
> fidelity was unspecified, so every prefill test could pass while Step 3 would arrive empty for
> every real applicant — silent HU-03 failure, no error, no log.
>
> **Re-evidence (authoritative for these rows now):**
> 1. Connected smoke + against Portal real → `unlocked` + hydrated identity fields.
> 2. Commit `e49b23f` — mock aligned to Hub+EN (+ `ciudad`/`space_id` traps); mapper reads only
>    contract keys; `test_obsolete_double_names_alone_do_not_hydrate` prevents the lying-mock
>    aliases from returning as “compatibilidad”.
>
> Do **not** treat the original 171-test green run alone as proof of Prefill hydration. The
> conclusion (MET) stands; the backing evidence is the smoke + `e49b23f`, not that first suite.

### Seguridad
| Criterion | Status | Evidence |
|---|---|---|
| Secret never in bundle/API responses/repo | **MET** | `test_portal_gate_secret_hygiene.py` (11 tests, pass); frontend source grep for `PORTAL_HUB_API_SECRET`/`PORTAL_HUB_API_KEY`/`NEXT_PUBLIC.*PORTAL` returns zero hits; bundle-grep itself was a manual check (task 7.3, documented in BIT-021) — not re-run here (would require a full `npm run build`, out of scope for this verify pass given the source-level checks already pass) |
| Signing only in backend | **MET** | no `signing`/`auth.py` counterpart in `src/frontend` |
| Logs exclude secret/signature/canonical, include `error_code`/`api_key`/folio/latency | **MET** | §2.6 above |

### Pruebas
All four "Pruebas" DoD rows — **MET**, evidenced by the 171-test REQ-013-scoped pass count above.

### Entrega
| Criterion | Status | Evidence |
|---|---|---|
| Assumed-contract mock gone from all environments | **MET** | |
| `portal-mock.py` rewritten to real contract + HMAC **and** payload keys (§4.6) | **MET** | HMAC from Slice E; Hub+EN payload + traps in `e49b23f` |
| Double rejects bad signature (401) and missing headers (401) | **MET** | `test_bad_signature_rejected`, `test_unsigned_request_rejected` |
| Per-environment credential pair (RN-020) | **PARTIAL** | Live pair loaded in gitignored `.env` for connected smoke (`bh_live_…`). Second distinct pair for a dedicated staging env still required if staging exists apart from prod — DoD row cannot fully tick otherwise |
| Connected smoke against real Portal | **MET** | Folio `BCE-20260717-121058-4083` → `200 unlocked`, `quotation_in_progress`, hydrated `lead_prefill` (2026-07-28) |
| Connected negative smoke (invalid secret → system error, not folio-rejected) | **MET** | Wrong secret → `502` + `INTEGRATION_AUTH_FAILURE`, no retry CTA; restored (2026-07-28) |
| NTP verified on Hub backend | **MET (local)** / **open on staging/prod hosts** | Host↔backend skew ≤1s; host vs `time.apple.com` +0.085s. Repeat on deploy hosts |
| Living docs updated (API-024, ARQ-001, BIT) | **MET** | vault BIT-021 + REQ-013 §4.6 VERIFICADO |
| RISK-4 closed in REQ-012 | **MET per DoD citation** | |

---

## 4. Task completion vs. code state (tasks.md)

As of `e49b23f` / tasks 7.4–7.5 marked done for the smoke gate: checked tasks correspond to real
passing code and connected evidence. Remaining operational (not code) gaps: task **0.2** / WARNING-1
(Sigao `proxy_intercept_errors`) and RN-020’s second pair if staging is a separate environment.

---

## 5. Issues

### CRITICAL
None.

### WARNING

**WARNING-1 — Edge-proxy `502` interception remains unverified while already live (design §14, tasks.md 0.2).**
- **What:** The shared edge proxy in front of this stack (outside this repository) has not been confirmed to pass `502` responses through unmodified. B2, which introduces the `502` for `INTEGRATION_AUTH_FAILURE`, has already merged into the tracker branch.
- **Where:** `src/backend/app/api/portal_gate_http.py:35` (`PORTAL_AUTH_FAILURE_HTTP_STATUS`), `openspec/changes/req-013-portal-hmac/tasks.md:61` (task 0.2, still unchecked).
- **Why it matters:** if that external proxy intercepts `502`s (a common default), an applicant hitting an auth-failure would see the proxy's own error page instead of Hub's frozen "no call to action" copy — silently defeating HU-04, with no way to detect it from inside this repo.
- **Fix:** confirm with whoever operates the shared edge proxy before/at the next deploy; if it intercepts 502s, flip `PORTAL_AUTH_FAILURE_HTTP_STATUS` to `503` and the matching `gate-error.ts` fallback row (both already documented as a 2-line change). This is not something `sdd-verify` can resolve — track it as a release gate, not a code defect.

**WARNING-2 — CLOSED (2026-07-28).** Dedicated regression test added:
`test_comentarios_over_300_words_survives_prefill_without_word_cap` (301 words,
prefill → submit schema contrast with RN-006). DoD citation in REQ-013 updated to
point at the real test node id. Commit `e1c0bdf` on `feat/req013-07-rollout-hygiene-docs`.

### SUGGESTION

**SUGGESTION-1 — Playwright default parallelism flakes against this dev stack.**
`tests/e2e/solicitud-gate.spec.ts` times out intermittently under the default 4 workers (cold
Turbopack compiles racing each other) but passes 9/9 deterministically at `--workers=1`. Not a
REQ-013 defect — Playwright config already acknowledges Turbopack latency in a comment — but
worth tuning `workers` down (or pre-warming the dev server) for this spec/environment if it is
ever run in CI against a dev-mode frontend.

**SUGGESTION-2 — No end-to-end (HTTP-level) test asserts truncation on the actual gate response body.**
Truncation is fully covered at the pure `prefill.py` unit level and indirectly via the
`portal-mock.py` >5000-char fixture (verified manually per the Slice C commit note), but there is
no `test_public_quote_gate.py` case asserting `lead_prefill.requerimientos_especiales` is
`<= 5000` chars and carries the marker when returned over the actual `/validate-folio` HTTP
response. Low priority — the seam is already proven at the unit boundary per design §12's
intended test strategy — but would close the loop for the DoD's "the mapped value... is at or
under the cap" scenario end-to-end.

**SUGGESTION-3 — `.env.example` and the standalone `npm run build` bundle grep (task 7.3) were not re-executed in this pass.**
Both were read as file-system-restricted from this verification session (sandboxing denied
`.env.example`) or judged too costly to re-run (full frontend production build). Source-level
grep for the credential literals across `src/frontend` returned zero hits, which is strong
corroborating evidence, but the DoD's authoritative bundle-grep check (the "one the DoD actually
asks for" per design §9) was taken on the trust of BIT-021's manual record, not independently
re-run here. Recommend re-running it once before the tracker branch actually merges to `main`,
since it's cheap and closes the loop completely.

---

## 6. Readiness for `sdd-archive`

**Not ready to archive yet.** Code + connected smokes are closed. Two operational gates remain:

1. **WARNING-1 — Sigao edge proxy** (`proxy_intercept_errors` / 502 body preservation). Only item
   with live risk today; does not depend on Portal credentials. Fallback still two lines if it
   intercepts.
2. **RN-020 — second credential pair** if staging exists as a separate environment from prod. The
   DoD row that requires distinct pairs cannot be fully ticked while staging and prod share one.

Also closed since the original verify pass:
- WARNING-2 (`e1c0bdf`)
- Prefill key fidelity / lying-double correction (`e49b23f` + smoke) — see §3 addendum
- Connected smoke + / smoke − / local clock check (2026-07-28)

Recommend: `sdd-archive` only after Sigao confirmation and an honest RN-020 answer (second pair, or
documented decision that staging is not a separate credential domain).
