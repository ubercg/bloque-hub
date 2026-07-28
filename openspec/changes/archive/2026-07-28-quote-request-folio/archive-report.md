# Archive Report — `quote-request-folio` (REQ-012)

**Archived:** 2026-07-28
**Archived to:** `openspec/changes/archive/2026-07-28-quote-request-folio/` (copy — see "Tooling limitation" below)
**Status:** shipped, archived with a documented reconciliation and one minor living-doc gap. No CRITICAL issues.

## Summary

REQ-012 delivered a public, no-login, folio-gated 5-step quote-request wizard for BLOQUE Portal leads, reusing Hub's existing inventory/pricing/notifications machinery with a corrected pricing call (the `create_quote` pricing bug was NOT copied). 10 PRs shipped (#1–#10), including two post-hoc corrections: Phase 10 (`servicios_apoyo` fixed enum, not catalog) and Phase 11 (4R adversarial review: 1 BLOCKER + 4 CRITICAL + 2 WARNING + 1 SUGGESTION, all fixed with TDD), plus Phase 12 (rate limiting, the merge-to-main gate).

## Task Completion Gate

`tasks.md` had 3 unchecked items at archive time: 0.2, 9.1–9.5. Reconciled as follows:

| Task | Resolution |
|---|---|
| 0.2 (HTTP mapping for `NoPricingRuleError`) | **Reconciled — stale checkbox.** Task 3.2's own note defers it to PR #4; task 4.2 step 5 (checked) confirms the mapping shipped. No `apply-progress`/`verify-report` artifact exists for this older change to cite per the strict gate — reconciled directly from `tasks.md`'s own internal evidence at archive time. |
| 9.1–9.5 (living docs) | **Reconciled — stale checkboxes.** Verified directly against the Obsidian vault at archive time: `30-API/API-025-PublicQuoteRequests.md` exists, `20-Arquitectura/ARQ-001-Decisiones-Core.md` §15.6 was updated (per task 10.4), `50-Bitacora/BIT-012-Estatus-REQ-012.md` exists, and REQ-012's own DoD (§7) has all 19 checkboxes ticked `[x]`. Task 9.5 (TSK execution files) is vacuously satisfied — no `TSK-*` files were ever created for this change (confirmed via glob; work was tracked entirely via the SDD `tasks.md` artifact). |
| 0.3 | **Left unchecked, correctly.** This is REQ-012's own record that it never confirmed the real Portal contract — see RISK-4 closure below. Not reconciled, because it is historically accurate: REQ-012 shipped against an assumed contract. |

No CRITICAL issues exist for this change (it predates `sdd-verify`'s formal report format; the 4R adversarial review in Phase 11 served as the equivalent verification gate and found/fixed everything down to SUGGESTION level).

## Living-doc gap (non-blocking, noted for the record)

`10-Requerimientos/REQ-012-Solicitud-Cotizacion-Folio-Portal.md` frontmatter still reads `status: draft` despite all 19 DoD checkboxes being `[x]`. This is a minor inconsistency in the requirement file's own metadata, not a task-gate blocker. Recommend the user flip it to `status: done` directly in Obsidian (outside this tool's write scope for this session — see tooling limitation below regarding vault writes not attempted).

## RISK-4 — Portal contract assumption (superseded)

REQ-012 shipped against an **assumed** Portal response shape: public route `/api/public/space-event-requests/access/{folio}`, no authentication, eligibility read from `status` at the JSON root. This was tracked as task 0.3 / RISK-4, explicitly left open ("Still unconfirmed... proceed with the design's assumed shape").

**RISK-4 is now CLOSED**, by `req-013-portal-hmac` (archived immediately after this change, in the same session, per the mandated order). REQ-013 confirmed and implemented the real contract:
- Integration route `/api/integrations/bloque-hub/leads/{folio}/access` (not the assumed public route)
- Mandatory HMAC-SHA256 signing (not no-auth)
- Eligibility from `data.status` (not root-level `status`)

See `req-013-portal-hmac`'s archive report for full detail. This closure is also recorded in the merged `quote-gate-api` baseline spec's Notes section and in this change's own `spec.md` copy (updated inline at archive time).

## Spec Merge

Two baseline domains were created from this change's monolithic `spec.md` (18 requirements, no pre-existing domain split):

| Domain | Requirements from REQ-012 | Rationale |
|---|---|---|
| `openspec/specs/quote-gate-api/spec.md` | Folio format validation (RN-017); Folio gate — Portal status validation (RN-001/002/003); Portal client resilience; Revalidation on submit (RN-004); Public no-login access (RN-002, config) | The Hub-facing gate/submit API surface — later extended by `req-013-portal-hmac` with 5 more requirements (status-to-HTTP mapping, `lead_prefill`). Landed FIRST (this change), so REQ-013's additions merge in cleanly second without collision. |
| `openspec/specs/quote-request-submission/spec.md` | Step 1-5 field validation (RN-005–011, RN-014); Multi-space/multi-day pricing (RN-012); Atomic persistence (RN-013); Confirmation email (RN-016); Documents (RN-015) | Wizard-internal validation/persistence/pricing/email — untouched by `req-013-portal-hmac`, which only changed the Portal integration and gate API surface. |

No content was destructively overwritten: REQ-012's requirements as written describe Hub's gate/submit behavior toward the solicitante (no-login access, RN-003 message, RN-004 revalidation) and do not hard-code the specific outbound route/auth/status-field details that later proved wrong — those details lived only in the closing "Risks / Assumptions" note (now updated in-place) and in `tasks.md`'s own task-0.3/0.2 notes. All 16 requirements carried forward verbatim into the two new domains; 0 removed, 0 modified.

## Tooling limitation (transparency note)

This session's tool set for `sdd-archive` was `Read`, `Write`, `Edit`, `Glob`, and the Engram MCP tools — **no Bash/shell tool, no file-move or file-delete tool was available.** The "move to archive" step was therefore performed as a **copy**: every artifact (`proposal.md`, `spec.md`, `design.md`, `explore.md`, `tasks.md`, this report) was written to `openspec/changes/archive/2026-07-28-quote-request-folio/` via the `Write` tool. **The original `openspec/changes/quote-request-folio/` directory still exists on disk and was not deleted.** The user should remove it manually (e.g. `git rm -r openspec/changes/quote-request-folio/` or `rm -rf`) as part of reviewing this archive, or grant a shell-capable tool in a follow-up session to complete the move cleanly.

## Artifacts

- `openspec/changes/archive/2026-07-28-quote-request-folio/{proposal,spec,design,explore,tasks}.md` (copies)
- `openspec/specs/quote-gate-api/spec.md` (new baseline domain)
- `openspec/specs/quote-request-submission/spec.md` (new baseline domain)
- Engram: `sdd/quote-request-folio/archive-report`
- ⚠️ `openspec/changes/quote-request-folio/` (original) — NOT deleted, needs manual cleanup
