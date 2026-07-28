# Archive Report — `req-013-portal-hmac` (REQ-013)

**Archived:** 2026-07-28
**Archived to:** `openspec/changes/archive/2026-07-28-req-013-portal-hmac/` (copy — see "Tooling limitation" below)
**Status:** archived as **shipped with known open operational items**. No CRITICAL issues. Two WARNING-level items remain open and are recorded honestly below — they are operational (external-dependency) gaps, not code defects.

## Summary

REQ-013 replaced REQ-012's assumed BLOQUE Portal contract with the real, confirmed one: the
integration route `/api/integrations/bloque-hub/leads/{folio}/access`, mandatory HMAC-SHA256
request signing, and eligibility read from `data.status` (not root-level `status`). It also added
`lead_prefill` to hydrate wizard Step 3 from data Portal already has, and fixed a pre-existing
frontend defect that mislabeled unknown gate errors as folio rejections.

Delivered as 7 chained PRs on a `feature-branch-chain` tracker (`feat/req013-portal-hmac`), all
child PRs merged in dependency order, culminating in the tracker merging to `main` at commit
`8557e45` (merge commit, `--no-ff`, revertible whole with `git revert -m 1 8557e45`).

## Verification disposition

`verify-report.md` (dated 2026-07-28, same session) concluded **PASS WITH WARNINGS** — no CRITICAL
findings, but originally recommended *"do not archive yet"* pending two items. Both are recorded
here honestly rather than glossed over:

### WARNING-1 — Sigao edge proxy `502` interception, unverified

REQ-013's Slice B2 introduces `502 Bad Gateway` as the HTTP status for
`INTEGRATION_AUTH_FAILURE` (`PORTAL_AUTH_FAILURE_HTTP_STATUS` at
`src/backend/app/api/portal_gate_http.py:35`). Whether the **shared edge proxy** in front of this
stack — which lives outside this repository — runs `proxy_intercept_errors` (a common default for
reverse proxies fronting upstream error pages) was never confirmed.

**This is narrower than first feared.** The frontend's status-code fallback in
`features/quote-wizard/gate-error.ts` handles a proxy that only replaces the response **body** — the
authoritative discriminator is `detail.reason`, read first; `case 502 → auth_failure` is only the
*fallback* row, exercised when `reason` is absent. It breaks only if the intercepting proxy also
**rewrites the HTTP status code itself** (not just the body), which is a less common (though not
rare) proxy configuration.

**Documented fallback, if the proxy is later found to intercept:** flip
`PORTAL_AUTH_FAILURE_HTTP_STATUS` (`src/backend/app/api/portal_gate_http.py:35`) from `502` to
`503`, and flip the two matching rows in `features/quote-wizard/gate-error.ts` (`502 → auth_failure`
/ `503 → unavailable` swap). A 2-line change, already documented in `design.md` §5 and §14.

**Status: still open at archive time.** This repository's own `infra/nginx/nginx.conf` was
re-verified clean (no `proxy_intercept_errors`/`error_page`), but the *shared* edge proxy outside
this repo cannot be verified from here. Track as a release/ops gate, not a code defect.

### RN-020 — second credential pair for a dedicated staging environment

REQ-013 requires a distinct `PORTAL_HUB_API_KEY`/`PORTAL_HUB_API_SECRET` pair per environment
(staging and production MUST NOT share one). Only **one** live pair was received and loaded
(gitignored `.env`, used for the connected smoke against production). If a staging environment
exists separately from production, a second, distinct pair is still required before that DoD row
can be fully ticked. This is an external-dependency gap (credential delivery from the Portal team),
not a code defect — the code already enforces "no default, must be present" per environment (D9).

## Decision to archive despite open WARNINGs

Per this session's explicit instruction, this change is archived now with both items recorded
plainly, rather than waiting. Justification against the `sdd-archive` skill's rules:

- **No CRITICAL issues exist** — the skill only hard-blocks archive on CRITICAL verification
  findings ("NEVER archive a change that has CRITICAL issues in its verification report"). Neither
  WARNING-1 nor RN-020 is CRITICAL.
- **Both are documented, non-code, external-dependency gaps** — WARNING-1 needs confirmation from
  whoever operates the shared edge proxy (outside this repository); RN-020 needs a second
  credential pair delivered by the Portal team for a staging environment that may not yet exist
  separately from production. Neither can be resolved by more code changes in this repo.
- **This is recorded as an intentional partial archive**, per the skill's allowance: "If the user
  explicitly approves a non-critical partial archive... record the exact reason in the archive
  report and mark the archive as intentional-with-warnings." This report is that record.

**This archive is marked intentional-with-warnings.**

## Task Completion Gate

`tasks.md` had 4 unchecked items at archive time: 0.1, 0.2, 0.3, 0.4 — all in Phase 0
("Confirmations"). All four are correctly unchecked, not stale:

| Task | Disposition |
|---|---|
| 0.1 (truncation marker copy) | Informational/no-action — the placeholder value shipped by default since no correction was ever received (explicitly non-blocking per its own text) |
| 0.2 (edge-proxy verification) | **Genuinely unresolved** — see WARNING-1 above. Correctly left unchecked; `verify-report.md` §2.7 explicitly confirms this was "never claimed resolved" |
| 0.3 (auth-failure copy, frozen) | Informational/no-action, already resolved at design time |
| 0.4 (`ciudad` ignored, frozen) | Informational/no-action, already resolved at design time |

All Phase 1–7 implementation tasks (1.1–7.7) are checked `[x]`. Per the `sdd-archive` skill, Phase 0
confirmation/informational items are not "implementation tasks" in the sense the task-completion
gate cares about — none were reconciled or stale-checkbox-repaired; the record is accurate as-is.

## Verified end-to-end against Portal production

- **Positive smoke (2026-07-28):** folio `BCE-20260717-121058-4083` → `200 unlocked`,
  `quotation_in_progress`, `lead_prefill` hydrated with identity fields.
- **Negative smoke (2026-07-28):** invalid secret → `502` + `INTEGRATION_AUTH_FAILURE`, no call to
  action rendered (per D1/D4 frozen copy).

## Defects found only by the connected smoke, both fixed

1. **Lying test double — obsolete `lead_prefill` key names.** The local double
   (`portal-mock.py`) and `map_lead_prefill` originally used invented key names
   (`nombre_solicitante`, `email_solicitante`, `telefono_solicitante`, `numero_invitados`, …) that
   Portal never actually sends. Portal real sends Hub-canonical keys (`nombre_completo`,
   `correo_institucional`, …) plus English synonyms in the same object. 25 green tests were
   validating a contract that did not exist, and Step 3 would have arrived **empty for every real
   applicant, with no error and no log** — a silent HU-03 failure. Fixed in commit `e49b23f`, with
   a dedicated regression test (`test_obsolete_double_names_alone_do_not_hydrate`) asserting the
   obsolete names alone do NOT hydrate anything.
2. **`space_id` trap field.** Portal sends a literal `space_id` key from its own catalog in the
   `lead_prefill` object. RN-015 (never derive a `space_id` from `lead_prefill`) was extended to
   explicitly forbid mapping this field — it is now an intentionally-ignored trap, alongside
   `ciudad`.

## RISK-4 closure

RISK-4 (REQ-012's unconfirmed Portal contract assumption, tracked as `quote-request-folio` task
0.3) is **CLOSED** by this change. The real contract is now implemented end-to-end and verified
against production. This closure is also recorded in `quote-request-folio`'s own archive report
(archived earlier in this same session, per the mandated order) and in the `portal-gate-integration`
baseline spec's Notes section.

## Spec Merge

| Domain | Action | Detail |
|---|---|---|
| `openspec/specs/portal-gate-integration/spec.md` | **Created** (new domain) | Full copy of REQ-013's delta spec — 12 requirements. No REQ-012 predecessor existed under this name. |
| `openspec/specs/quote-gate-api/spec.md` | **Extended** (5 requirements ADDED) | REQ-012's 5 pre-existing requirements preserved verbatim; REQ-013's 5 new requirements (exhaustive status-to-HTTP mapping, `lead_prefill` exposure scope, `comentarios` truncation, prefill null-tolerance, field-mapping constraints) appended. No REQ-012 requirement modified or removed — the two sets share no requirement names and are complementary. |
| `openspec/specs/quote-wizard-frontend/spec.md` | **Created** (new domain) | Full copy of REQ-013's delta spec — 4 requirements. REQ-012 never defined a domain by this name (its frontend concerns live in `quote-request-submission` instead). |

**Merge correction note:** during this session, the `quote-gate-api` merge was initially performed
incorrectly (the 5 REQ-013 requirements were duplicated instead of appended once). This was caught
and corrected before archiving completed — the final file contains each requirement exactly once,
with a provenance note distinguishing REQ-012-origin vs REQ-013-origin requirements.

## Tooling limitation (transparency note)

Same limitation as `quote-request-folio`'s archive: no Bash/file-move/delete tool was available in
this session. The "move to archive" step was performed as a **copy** via the `Write` tool — every
artifact (`proposal.md`, `design.md`, `explore.md`, `specs/{portal-gate-integration,quote-gate-api,
quote-wizard-frontend}/spec.md`, `tasks.md`, `verify-report.md`, this report) was written to
`openspec/changes/archive/2026-07-28-req-013-portal-hmac/`. **The original
`openspec/changes/req-013-portal-hmac/` directory still exists on disk and was not deleted.** The
user should remove it manually as part of reviewing this archive.

## Artifacts

- `openspec/changes/archive/2026-07-28-req-013-portal-hmac/{proposal,design,explore,tasks,verify-report,archive-report}.md` (copies)
- `openspec/changes/archive/2026-07-28-req-013-portal-hmac/specs/{portal-gate-integration,quote-gate-api,quote-wizard-frontend}/spec.md` (copies)
- `openspec/specs/portal-gate-integration/spec.md` (new baseline domain)
- `openspec/specs/quote-gate-api/spec.md` (extended baseline domain, now 10 requirements)
- `openspec/specs/quote-wizard-frontend/spec.md` (new baseline domain)
- Engram: `sdd/req-013-portal-hmac/archive-report`
- ⚠️ `openspec/changes/req-013-portal-hmac/` (original) — NOT deleted, needs manual cleanup

## Open follow-ups for the user

1. Confirm with whoever operates the shared edge proxy whether it runs `proxy_intercept_errors` on
   `502` responses. If yes, flip `PORTAL_AUTH_FAILURE_HTTP_STATUS` to `503` in
   `src/backend/app/api/portal_gate_http.py:35` and the matching row in
   `features/quote-wizard/gate-error.ts`.
2. Provision a second, distinct `PORTAL_HUB_API_KEY`/`PORTAL_HUB_API_SECRET` pair for staging, if
   staging exists (or will exist) separately from production.
3. Manually remove `openspec/changes/quote-request-folio/` and `openspec/changes/req-013-portal-hmac/`
   (the un-deleted originals) once this archive copy has been reviewed.
4. Consider flipping REQ-012's Obsidian frontmatter `status: draft` → `status: done`, since all 19
   DoD checkboxes are ticked (noted in `quote-request-folio`'s archive report).
