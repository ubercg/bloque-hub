# Proposal — req-013-portal-hmac

**Change:** `req-013-portal-hmac`
**Requirement:** REQ-013 — Real BLOQUE Portal integration: definitive contract and HMAC signing
**Phase:** propose
**Date:** 2026-07-28
**Artifact store:** openspec (mirrored in Engram at `sdd/req-013-portal-hmac/proposal`)
**Inputs:** `openspec/changes/req-013-portal-hmac/explore.md`, REQ-013 (Obsidian vault, source of truth)

> REQ-013 §11 decisions are **closed**. RN-010, RN-019, RN-020, RN-021 and RN-022 are settled
> and are treated here as constraints, not as options.

---

## 1. Intent

**Problem.** The `portal_gate` client implements a contract that Portal never shipped. It reads the
status at the JSON root (`client.py:24,76`) while the real contract nests it at `data.status`.
Pointed at the real Portal, `body.get("status")` returns `None` for every response and
`_extract_status` falls through to `NOT_ELIGIBLE` (`client.py:79`). **Every eligible folio is
rejected.** The path is also wrong and authentication is absent entirely.

**Why now.** RISK-4 stopped being a risk and became a confirmed production blocker. Portal published
and verified the definitive contract on 2026-07-28. Until Hub migrates, the Portal → Hub funnel
cannot be switched on at all — not degraded, not partially working: zero applicants can open the
wizard.

**What success looks like.**

| Outcome | Observable signal |
| :--- | :--- |
| The funnel works against the real system | A folio in `quotation_in_progress` unlocks the wizard end to end |
| Lead PII is protected by cryptography, not obscurity | Every outbound request carries a valid HMAC-SHA256 signature; the double rejects unsigned requests |
| Applicants stop re-typing what they already gave Portal | Step 3 arrives hydrated from `lead_prefill`, every field editable |
| Operators can tell "Portal is down" from "our credentials are wrong" | `INTEGRATION_AUTH_FAILURE` is a distinct state with a stable `error_code` in the log |
| Applicants are not invited to retry an action that cannot succeed | The auth-failure message differs from both the folio-rejection and the Portal-unavailable messages |
| The assumed contract cannot come back | The local double verifies signatures; no code path reaches the old public route |

---

## 2. Scope

### 2.1 In scope

| # | Area | Work |
| :---: | :--- | :--- |
| 1 | `portal_gate/signing.py` (new) | Pure canonical-string + HMAC-SHA256/Base64 functions |
| 2 | `portal_gate/auth.py` or same module | `httpx.Auth` subclass that signs from the normalized wire path |
| 3 | `portal_gate/client.py` | Integration route, `data.status` parsing, `error_code` taxonomy, `INTEGRATION_AUTH_FAILURE`, RN-012 retry policy, contract-violation handling, log markers |
| 4 | `core/config.py:82-87` | Retire `PORTAL_API_KEY`; add required `PORTAL_HUB_API_KEY` / `PORTAL_HUB_API_SECRET` with no repository defaults |
| 5 | `api/public.py:108-112` | `FolioValidateResponse` grows `lead_prefill` |
| 6 | `api/public.py:143-155`, `:544-555` | One shared, exhaustive status → HTTP mapping used by gate **and** submit revalidation |
| 7 | `solicitud/page.tsx:18-62` | Branch on `detail.reason`; new auth-failure state; **fix the pre-existing mislabeling defect at lines 60-61** |
| 8 | `quote-wizard.store.ts` | Bulk prefill-hydrate action + informational reference fields; new `gateStatus` members |
| 9 | Step 3 / Step 2 wizard UI | Consume hydrated values; render `fecha_tentativa` and `espacio_requerido` as reference only |
| 10 | `portal-mock.py`, `docker-compose.override.yml` | Rewrite the double to the real contract with genuine HMAC verification (RN-019) |
| 11 | `tests/test_portal_gate_client.py` | Full rewrite to the real contract |
| 12 | `tests/test_public_quote_gate.py`, `tests/test_public_quote_submit.py` | New coverage only — existing tests keep passing |
| 13 | Living documentation | API-024 rewrite, REQ-013 DoD, bitácora, RISK-4 closure in REQ-012 |

**On item 7 — the pre-existing frontend defect is deliberately in scope.**
`page.tsx:60-61` currently records *any* unclassified failure as
`setGateStatus('not_eligible', GENERIC_ERROR_MESSAGE)`. A dropped connection or an unexpected 500 is
therefore stored as a folio rejection. This predates REQ-013, but it is included here for two
reasons: (a) that exact branching block is being rewritten anyway to add the new state, so fixing it
costs a few lines instead of a separate change; (b) it is the **same category confusion RN-011
forbids**, expressed on the frontend instead of the backend. Shipping a backend that scrupulously
refuses to call an auth failure a folio rejection, on top of a frontend that calls a network timeout
a folio rejection, would be incoherent.

### 2.2 Out of scope — carried from REQ-013 §8

* Redesigning the 5-step wizard or its UX (REQ-012 owns it).
* Changing the lead state machine in `bloque_portal`.
* Hub → Portal callback/webhook on quote creation (`cotizacion_enviada`).
* Mapping Portal's space catalog to Hub inventory.
* Signature v2 (canonicalized query string, body hash) — only applies if the endpoint stops being a
  parameterless `GET`.
* Strict anti-replay with a nonce store inside the ±300 s window — a Portal-side decision.
* Credential persistence in the database with an administration UI.
* Caching the gate result — eligibility is read live.
* End-user authentication in the public wizard.

### 2.3 Out of scope — observability carve-out (REQ-013 §6, §8, decision 7 of §11.1)

The project has **no** alerting infrastructure: no Sentry, no Prometheus, no webhooks, no structured
logging configuration. This change delivers **stable, searchable log markers only** —
`portal_gate.auth_failure` and `portal_gate.contract_violation`. Explicitly not delivered here:

* Structured/JSON logging configuration or a logging framework migration.
* Log aggregation or shipping.
* `401` streak detection and thresholds.
* Notification of operations.

These require infrastructure the project does not have; an acceptance criterion such as "alerts
operations" would be unverifiable and would be ticked off in bad faith. Alert wiring is its own
requirement, and the markers this change establishes are the seam it will hook into.

### 2.4 Non-goals specific to this change

* **Do not** relax REQ-012's 300-word rule on `descripcion_evento` (RN-006 of REQ-012).
* **Do not** raise the 5000-character cap on `requerimientos_especiales` (see D3).
* **Do not** "unify" the gate and submit revalidation paths — see §3.
* **Do not** derive `space_id` from `espacio_requerido` (RN-015) or preselect a Step 2 date from
  `fecha_tentativa` (RN-022).
* **Do not** render `data.status_label` to the applicant (RN-010) or parse Portal's `message` field.

---

## 3. Invariants to preserve, not to build

Two properties the requirement asks for are **already true**. The work is to keep them true through
a rewrite, not to create them. Downstream phases must not plan work that "fixes" them.

| Invariant | Current evidence | Obligation |
| :--- | :--- | :--- |
| **RN-016** — gate and submit revalidation use one path and one mapping | `public.py:144` and `public.py:545` both call the identical `portal_gate_client.validate_folio(folio)` with identical exception handling. There is no duplicated path to unify | Keep it single. Adding the new state must not fork the two sites |
| **RN-017** — the signing secret never reaches the frontend | Repository-wide grep for `PORTAL_HUB` / `PORTAL_API_KEY` / `X-Api-Key` under `src/` hits only `client.py` and `config.py`. No `NEXT_PUBLIC_` exposure exists | Keep it closed. `lead_prefill` travels to the browser; credentials must not |

**The RN-016 trap this change introduces.** Both call sites end with
`if portal_status != PortalFolioStatus.ELIGIBLE: → 403 FOLIO_NOT_ELIGIBLE`
(`public.py:151-155`, `:551-555`). Adding `INTEGRATION_AUTH_FAILURE` as an enum member **without
touching that branch** makes an authentication failure silently render as "folio not enabled" — the
exact outcome RN-011 forbids, arriving through a catch-all `else` rather than through a decision.

Recommendation: replace the catch-all with **one shared, exhaustive mapping helper** consumed by
both call sites. Any future `PortalFolioStatus` member that is not mapped must fail loudly rather
than default to `FOLIO_NOT_ELIGIBLE`. This converts RN-016 from an incidental property (two call
sites that happen to be identical) into a structural one (two call sites that cannot diverge).

---

## 4. Decisions this proposal resolves

The exploration surfaced four questions REQ-013 did not anticipate. Each is resolved below with an
explicit recommendation and its tradeoffs.

### D1 — How the frontend distinguishes `INTEGRATION_AUTH_FAILURE`

**Context.** `page.tsx:49-62` branches purely on the HTTP status code and never reads the response
body. Meanwhile `public.py` already returns `detail.reason` on **every** error path —
`INVALID_FOLIO_FORMAT` (`:138`), `PORTAL_UNAVAILABLE` (`:148`), `FOLIO_NOT_ELIGIBLE` (`:154`). The
contract the frontend needs already exists; the frontend simply ignores it.

**Recommendation: both mechanisms, with `detail.reason` as the authoritative discriminator.**

| Layer | Decision |
| :--- | :--- |
| Discriminator | `detail.reason`, a new stable value for the auth-failure case. The frontend switches on it first |
| HTTP status | `502 Bad Gateway` for the auth failure — Hub's upstream rejected Hub, and it is not retryable. `503` keeps its existing "transient, retry later" meaning |
| Fallback | If `detail.reason` is absent or unrecognized, fall back to status-code branching, and from there to a **new** `unknown_error` state — never to `not_eligible` |
| Typing | Model reasons and gate states with the const-object + extracted-type pattern, so the reason list has one source of truth and is exhaustively checkable |

**Why `reason` is the discriminator and not the status code.** HTTP status codes are a coarse,
shared channel: each new product state would cost a status code, and status codes carry meaning for
proxies, CDNs, uptime monitors and browsers that Hub does not control. `reason` is Hub's own
namespace, already populated, and it survives the next state at zero contract cost.

**Why the status code still changes.** Leaving the auth failure on `503 Service Unavailable` makes
the HTTP layer assert something false — "transient, try later" — about a deterministic failure. That
misleads intermediaries that retry `503`, and it corrupts availability metrics by counting a
configuration error as downtime. `502` is honest at the protocol layer while `reason` carries the
product meaning.

**Tradeoffs considered.**

| Option | Verdict |
| :--- | :--- |
| New status code only | Cheapest diff, but burns a status code per state and leaves the frontend structurally unable to distinguish anything the status code cannot express. **Rejected as the sole mechanism** |
| `detail.reason` only, keep `503` | No status-code churn, but the HTTP layer keeps lying about retryability. **Rejected as the sole mechanism** |
| Both, `reason` authoritative | Small extra contract note plus one edge-proxy verification. **Chosen** |

**Risk, and why the choice is reversible.** An intermediary with `proxy_intercept_errors on` would
replace the `502` body with its own error page and destroy `detail.reason`. The repository's own
config (`infra/nginx/nginx.conf`) does **not** set it, but the shared edge proxy referenced in recent
commits lives outside this repository and must be verified during design. If it cannot be verified,
fall back to `503` + `reason` — because `reason` is authoritative, that fallback changes one backend
constant and **zero** frontend logic.

**Judged against RN-011 and HU-04.** The applicant-facing copy for this state must read as a system
fault with no call to action — no "intenta de nuevo", no "verifica el folio". It must be distinct
from both REQ-012's folio-not-enabled message and the Portal-unavailable message, which *does* invite
a retry. Copy stays in Hub (`page.tsx:20-24`), per RN-010.

### D2 — Precedence between the two retry mechanisms

**Context.** The existing timeout/5xx loop (`client.py:98-141`, bounded by `PORTAL_RETRY_ATTEMPTS`
clamped to 1–5) and RN-012's single re-fire on `TIMESTAMP_EXPIRED` are triggered by different
conditions and the requirement never defines their interaction.

**Recommendation: two independent mechanisms, separate budgets, different layers.**

| Mechanism | Lives in | Triggers on | Budget |
| :--- | :--- | :--- | :--- |
| Transport retry loop | The client's request loop | Timeout, connect error, `5xx`, and now `429` with backoff | `PORTAL_RETRY_ATTEMPTS` (1–5) |
| RN-012 re-fire | The signing/auth layer, inside a single transport attempt | `401` + `error_code = TIMESTAMP_EXPIRED`, and nothing else | Exactly **one**, per `validate_folio` call |

**Explicit answers.**

1. A re-fired-then-still-`401` request **does not** consume a `PORTAL_RETRY_ATTEMPTS` slot.
2. Any `401` is terminal for the transport loop, so at most one transport attempt can ever reach a
   `401`. Therefore a `TIMESTAMP_EXPIRED` path costs **exactly two** HTTP requests, worst case,
   regardless of how `PORTAL_RETRY_ATTEMPTS` is configured.
3. After the re-fire, a `401` of **any** `error_code` resolves immediately to
   `INTEGRATION_AUTH_FAILURE` with no further attempts.
4. `MISSING_CREDENTIALS`, `UNKNOWN_API_KEY`, `INVALID_SIGNATURE` and `MALFORMED_TIMESTAMP` are never
   re-fired at all (RN-012).
5. Every attempt, re-fire included, generates a fresh timestamp and a fresh signature (RN-006).

**Why separate budgets.** The two mechanisms answer different questions. The loop asks "is Portal
reachable and healthy?"; the re-fire asks "was my signature stale by a hair?". Sharing a budget would
make clock-skew tolerance vary with an unrelated operations knob, and — worse — would let a
completely misconfigured secret burn `N` attempts against a 60 req/min rate limit, which RN-012
exists specifically to prevent.

**Tradeoff.** Two retry mechanisms in one client is more surface than one. Mitigated by keeping them
in different layers with no shared state: the re-fire is invisible to the loop, and the loop never
inspects `error_code`. Confining the re-fire to the auth layer is what keeps the already-dense
transport loop from growing a second, differently-shaped branch.

### D3 — The `requerimientos_especiales` 5000-character cap

**Context.** `crm/schemas.py:193` declares `requerimientos_especiales: str | None = Field(None,
max_length=5000)`. Portal's `comentarios` is free text from a commercial lead with no character
bound. RN-013 states prefill is best-effort and **never blocking**; a prefilled value that makes the
form fail validation is blocking by definition, and it fails on text the applicant never wrote —
precisely the failure mode RN-021 was written to prevent, reappearing one field over.

**Recommendation: truncate server-side, at the prefill mapping boundary, to the schema's own cap.**

| Aspect | Decision |
| :--- | :--- |
| Where | Backend, in the `lead_prefill` mapper, before the value ever leaves Hub's API |
| To what | The submit schema's cap, referenced as a single shared constant so the two can never drift |
| Marker | Append a short Hub-authored truncation marker, counted **inside** the budget so the result still validates |
| Observability | Log `portal_gate.prefill_truncated` with the folio and the original length — never the content (PII) |
| Editability | Unchanged: the field stays fully editable (RN-013) |

**Why server-side.** The backend owns the validation rule, so the backend must own the truncation
that respects it. Truncating in the browser would let a future non-browser consumer of the same
response receive a value that cannot be submitted, and would place a backend invariant in a place
where nobody would look for it.

**Why a shared constant.** A hard-coded `5000` in the mapper is a bug waiting for the day someone
adjusts the schema. The cap must be declared once and read by both.

**Tradeoffs considered.**

| Option | Verdict |
| :--- | :--- |
| Raise the cap to fit any `comentarios` | Changes the validation contract for **every** applicant, prefilled or not, and touches REQ-012's data model to accommodate an integration edge case. Out of scope, wrong blast radius. **Rejected** |
| Drop the value when it exceeds the cap | Guarantees validity but silently discards information the lead deliberately wrote — and the commercial team is the loser. **Rejected** |
| Truncate on the frontend | Right effect, wrong owner. Leaks a backend invariant into the client. **Rejected** |
| Truncate at the prefill boundary | Value preserved up to the limit, form always submittable, invariant owned where it is defined. **Chosen** |

**Note on the DoD.** REQ-013's acceptance criterion exercises a >300-word `comentarios`, the case
RN-021 motivates. Roughly 300 words is ~2000 characters, comfortably under the cap, so that test does
**not** exercise this decision. The character-cap case needs its own explicit test.

### D4 — Signing layer structure

**Recommendation: confirmed — combine a pure `signing.py` with an `httpx.Auth` subclass**, with two
refinements the exploration did not specify.

| Component | Responsibility | Why |
| :--- | :--- | :--- |
| `signing.py` | Pure functions: build the canonical string, compute `base64(hmac_sha256_raw(secret, canonical))` | Zero HTTP dependency. The DoD's fixed known-vector test becomes a three-line unit test that cannot be broken by client refactors |
| `PortalHmacAuth(httpx.Auth)` | Read the path from the fully normalized `httpx.Request`, call `signing.py`, attach the three headers, own the RN-012 re-fire | `auth_flow(request)` receives the request **after** httpx has normalized it, so the signed path is provably what travels on the wire — RN-003's entire point |

**Why this beats inline signing.** Computing the path independently of what httpx sends makes RN-003
a coincidence rather than a guarantee. It holds today only because `FOLIO_PATTERN`
(`client.py:28`) restricts folios to digits and hyphens, so no percent-encoding-sensitive character
can occur. That safety is real but **inert and accidental** — it evaporates the day the folio format
changes, and it would evaporate silently, as a wave of `INVALID_SIGNATURE` responses in production.
The design must not rest on it.

**Refinement 1 — `raw_path` includes the query string.** In httpx, `URL.raw_path` returns path **and**
query as bytes. RN-004 requires the query string to be excluded from the canonical string. The auth
class must split on `?` and sign only the path portion. The endpoint is a parameterless `GET` today,
so this is currently a no-op — which is exactly why it will be forgotten unless it is specified now
and covered by a test.

**Refinement 2 — the re-fire requires reading the response body.** Deciding whether a `401` is
`TIMESTAMP_EXPIRED` means reading `error_code` from the body. httpx does not read the response body
before handing it to `auth_flow` unless the auth class declares
`requires_response_body = True`. Without that flag, the re-fire logic silently never fires. This is a
concrete, easy-to-miss implementation constraint and belongs in the design.

**Tradeoff accepted.** Coupling signing to httpx's `Auth` protocol makes the signing wiring
httpx-specific. That is acceptable because `portal_gate` is the only outbound HTTP client in the
codebase, the pure math stays client-agnostic in `signing.py`, and the two-step yield/receive/re-yield
protocol is a natural, well-bounded home for exactly one conditional re-fire.

---

## 5. Approach outline and sequencing

### 5.1 Why the test topology permits clean slicing

The two test layers fake Portal at different boundaries, and this is the single most useful fact for
sequencing under strict TDD:

| Suite | Fakes Portal at | Consequence |
| :--- | :--- | :--- |
| `test_portal_gate_client.py` | The **HTTP** layer — monkeypatches the `httpx.Client` constructor to inject an `httpx.MockTransport` (lines 21-42) | The client can be driven red → green in complete isolation. New HMAC known-vector and error-taxonomy tests plug into the existing transport seam |
| `test_public_quote_gate.py`, `test_public_quote_submit.py` | The **function** boundary — monkeypatch `public_module.portal_gate_client.validate_folio`, never touching HTTP | Entirely unaffected by the client rewrite. They need **new** coverage, not repair |

Rewriting the client therefore cannot break the integration suites, and the API-surface work can be
planned as additive coverage rather than as a migration.

### 5.2 Slice sketch

| Slice | Content | Depends on |
| :---: | :--- | :--- |
| **A** | `signing.py` pure functions + known-vector test; `PortalHmacAuth` with the `raw_path`/query and `requires_response_body` refinements; config adds `PORTAL_HUB_API_KEY` / `PORTAL_HUB_API_SECRET` | — |
| **E** | `portal-mock.py` rewritten to the real contract with genuine HMAC verification, ±300 s window, `data.*` envelope, `error_code` set; `docker-compose.override.yml`; explicit negative checks (bad signature → `401 INVALID_SIGNATURE`, no headers → `401 MISSING_CREDENTIALS`) | A (shares the canonical-string definition, not its code) |
| **B1** | Client happy path: integration route, auth wiring, `data.status` parsing, contract-violation handling. **Closes RISK-4** | A |
| **B2** | `error_code` taxonomy, `INTEGRATION_AUTH_FAILURE`, RN-012 retry policy, `429` handling, log markers; retire `PORTAL_API_KEY` and `X-Api-Key`; finish the `test_portal_gate_client.py` rewrite | B1 |
| **C** | `lead_prefill` on `FolioValidateResponse`, `comentarios` truncation at the mapper, the shared exhaustive status → HTTP mapping used by both call sites; new coverage in the two integration suites | B2 |
| **D** | Frontend: `detail.reason` branching, new gate states, the `page.tsx:60-61` defect fix, store hydrate action, Step 3 hydration, Step 2 reference display for `fecha_tentativa` / `espacio_requerido` | C |
| **F** | Living documentation (API-024 rewrite, bitácora, REQ-013 DoD, RISK-4 closure in REQ-012) and connected smoke tests | D + external credentials |

**Why E precedes B.** The double is not needed for B's tests — those use `MockTransport`. It is
needed so `docker compose up` stays coherent at every merge point. The moment B1 changes the route,
the old mock stops answering; landing E first means local development is never broken between merges.

**Why B splits at B1/B2.** Under strict TDD, test and implementation land together, so the client
rewrite cannot be split into "tests" and "code". It can be split by **behavior**: B1 is the happy
path and alone un-breaks the integration — real, independently shippable value. B2 adds the error
taxonomy on top. Without this split, B is the slice most likely to blow the review budget on its own.

**External dependency.** Credential delivery from the Portal team (REQ-013 §11.2) blocks **F only**.
Slices A through E build against fixed signature vectors and the local double, and must not be
sequenced behind it.

### 5.3 Review-size risk — stated honestly

| Slice | Rough changed lines |
| :---: | :---: |
| A | 150–250 |
| E | 250–350 |
| B1 | 250–400 |
| B2 | 300–500 |
| C | 200–300 |
| D | 250–400 |
| **Total** | **~1400–2200** |

This change spans the backend client, configuration, the API surface, the frontend store and page,
the test double, and two test layers. It will **very likely exceed 400 changed lines by a factor of
three or more**, and slice B2 may exceed 400 on its own.

**Chained PRs recommended: Yes.**
**400-line budget risk: High.**
**Decision needed before apply: Yes.**

`delivery_strategy` is `ask-on-risk`, so the orchestrator must resolve the PR-splitting question with
the user before `sdd-apply` runs. Compressing this into a single PR would produce a diff no reviewer
can meaningfully verify, on a change whose whole point is cryptographic correctness.

---

## 6. Risks carried into design

| # | Risk | Mitigation |
| :---: | :--- | :--- |
| 1 | The shared edge proxy (outside this repository) may intercept `502` and destroy `detail.reason` | Verify during design. Fallback is `503` + `reason`: one backend constant, zero frontend changes |
| 2 | Adding the enum member without changing the `!= ELIGIBLE` catch-all silently violates RN-011 | The shared exhaustive mapping helper of §3; unmapped states must fail loudly |
| 3 | `raw_path` carries the query string; signing it violates RN-004 | Split on `?` in the auth class; cover with a test even though it is a no-op today |
| 4 | `requires_response_body = True` omitted → the RN-012 re-fire silently never fires | Named as an explicit design constraint; cover with a test that asserts the re-fire actually occurs |
| 5 | Byte-identity of the signed path is currently safe only because `FOLIO_PATTERN` excludes encoding-sensitive characters | Sign from the normalized request, never from a reconstructed string. Add the explicit signed-path vs wire-path comparison test the DoD requires |
| 6 | Log markers are net-new conventions with no existing observability to extend | Accepted and carved out (§2.3). Deliver stable marker names; alerting is a separate requirement |
| 7 | `lead_prefill` carries lead PII to the browser | Return it only on a successful gate for the folio being queried; never echo it on submit, on errors, or in logs |
| 8 | Slice B2 alone may exceed the review budget | Flagged for `sdd-tasks`; split further by `error_code` group if needed |

---

## 7. Proposal question round

The orchestrator's brief settled the product decisions this proposal needed. The following are the
remaining product-level assumptions I made rather than asked. They are stated so the user can correct
any of them before `sdd-spec` and `sdd-design` run — none of them blocks proceeding.

1. **Truncation visibility.** I assumed a long `comentarios` should be **truncated with a visible
   marker** rather than silently cut or dropped, so the applicant can tell something was shortened
   and the commercial team does not lose the lead's intent entirely. If the preference is a silent
   cut, or dropping the field above the cap, say so — it changes D3 only.
2. **Auth-failure copy.** I assumed the applicant-facing message should be a system fault with **no
   call to action at all**, not even "contacta a soporte", since Hub has no support channel declared
   in REQ-012's copy. If a support contact should appear, that is a copy decision worth making now.
3. **`ciudad`.** REQ-013 §4.6 marks it informative and explicitly says Hub may ignore it. I assumed
   Hub **ignores** it — no store field, no display. Confirm if it should be shown somewhere.
4. **B1 as an independent release.** I assumed shipping the happy path first has real standalone
   value (it closes RISK-4 and restores the funnel) even though the error taxonomy arrives in a later
   PR. If the funnel must not be re-enabled until the full error handling is in place, B1 and B2
   should ship as one gated slice instead.

---

## 8. Next phase

`sdd-spec` and `sdd-design` may run in parallel. Both read this proposal.

* **`sdd-spec`** — turn REQ-013's DoD into verifiable requirements, including the two gaps the DoD
  does not cover: the `comentarios` character cap (D3) and the exhaustive status → HTTP mapping (§3).
* **`sdd-design`** — the signing layer per D4 including both refinements, the retry topology per D2,
  the error-contract shape per D1 with the edge-proxy verification, and the `lead_prefill` mapping
  and truncation boundary per D3.

Neither a specification nor a design is produced here by intent.
