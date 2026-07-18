
# Tasks: Solicitud de Cotización mediante Folio de BLOQUE Portal (`quote-request-folio`)

**Source:** REQ-012, `spec.md`, `design.md`, `proposal.md`.
**Delivery strategy:** `ask-on-risk` (see Review Workload Forecast at the end — this change is large and chained PRs are recommended).
**Locked decisions reflected here:**
- `Quote.portal_folio` + adjunct `quote_wizard_details` + adjunct `quote_wizard_documents` (Option B, confirmed).
- New service `create_public_quote_request` (does NOT reuse the buggy `create_quote` pricing call — calls pricing with `target_date: date` + `duration_hours: Decimal`).
- Portal gate httpx client with retry 2–3× backoff + 3-way error taxonomy (ELIGIBLE / NOT_ELIGIBLE / UNAVAILABLE).
- RN-004 revalidation happens BEFORE the write transaction is opened.
- Multi-space/multi-day atomic soft-hold via `check_group_availability` + `apply_soft_hold_for_quote`.
- Best-effort, non-blocking confirmation email — no `NotificationLog`.
- Tenant resolved via `settings.DEFAULT_TENANT_ID` (public endpoints, no JWT).
- New settings: `PORTAL_API_BASE_URL`, `PORTAL_RETRY_ATTEMPTS`, `PORTAL_API_KEY`, `LEGAL_REGLAMENTO_URL`, `LEGAL_AVISO_PRIVACIDAD_URL`, `WIZARD_DOCUMENTS_STORAGE_PATH`.
- Middleware `isPublicPage` whitelist fix for `/solicitud*`.
- **Documents = Option B**: new `quote_wizard_documents` table; submit endpoint is `multipart/form-data` (JSON `payload` part + `files[]`) from the first slice; reuses `MAX_KYC_FILE_BYTES` and existing MIME/size rules; RLS per tenant on the new table.

Each phase below is a reviewable work unit (work-unit-commits skill). Tests and docs ship in the same commit/PR as the behavior they verify, not split out.

---

## Phase 0 — RISK confirmations (blocking, do first)

- [x] 0.1 Confirm enum catalog values for `TipoEvento`, `CaracterEvento`, `Sector`, `ComoConociste`, `MontajeRequerido` against REQ-012/product before writing the migration (RISK-1, design §9). Freeze values in a short note in this tasks file or the PR description — enum values are costly to change post-migration.
  - **FROZEN (REQ-012 §4)**: `TipoEvento` = Firma de convenio, Conferencia, Taller / Workshop, Presentación, Networking, Rueda de prensa, Reunión institucional, Otro. `CaracterEvento` = Público, Privado, Gubernamental, Académico, Empresarial. `Sector` = Gobierno municipal/estatal/federal, Universidad / Institución educativa, Empresa privada, Organismo internacional, Organización civil, Startup / Emprendimiento, Otro. `ComoConociste` = Recomendación de otra institución, Redes sociales, Sitio web del Municipio, Ya he realizado eventos anteriores, Otro. `MontajeRequerido` = Estándar (mesas y sillas en U), Teatro, Aula, Cóctel, Protocolar para firma, Sin montaje. These supersede design.md §1.3's placeholder values and are implemented verbatim in migration `q1r2s3t4u5v6`.
- [ ] 0.2 Confirm HTTP mapping (409 vs 422) and UX copy for `NoPricingRuleError` on submit (RISK-3, design §9 / §4.4 table).
- [ ] 0.3 Confirm exact Portal `200` response body shape (status field name/values) for `GET /api/public/space-event-requests/access/{folio}` (RISK-4). If unavailable, proceed with the design's assumed shape and flag as a follow-up.
  - **Still unconfirmed as of Phase 2 (PR #2).** Proceeded per this task's own fallback instruction: implemented against the assumed shape (`{"status": "quotation_in_progress"}`), centralized in `PORTAL_STATUS_FIELD`/`PORTAL_ELIGIBLE_STATUS_VALUE` constants at the top of `modules/portal_gate/client.py` for a one-line swap once the real contract is confirmed.

*Depends on: nothing. Blocks: Phase 1 (migration needs 0.1), Phase 3 (needs 0.2), Phase 2 (needs 0.3).*

---

## Phase 1 — Backend data model + migration (PR #1)

- [x] 1.1 Add new enums (`TipoEvento`, `CaracterEvento`, `Sector`, `ComoConociste`, `MontajeRequerido`) to `crm/models.py`, matching frozen values from task 0.1.
- [x] 1.2 Add `Quote.portal_folio: str | None` column (`String(32)`, nullable, indexed) to `crm/models.py`.
- [x] 1.3 Add `QuoteWizardDetails` model (1:1 adjunct, all Step 1/3/4 fields + legal acceptance flags) per design §1.3, with `wizard_details` relationship on `Quote`.
- [x] 1.4 Add `QuoteWizardDocuments` model (Option B): `id`, `tenant_id`, `quote_id` FK, `storage_key`, `mime_type`, `size_bytes`, `original_filename`, `created_at`. Add relationship on `Quote` (1:N).
- [x] 1.5 Write Alembic migration `q1r2s3t4u5v6_add_portal_folio_and_wizard_details.py`:
  - `add_column("quotes", "portal_folio")`
  - partial unique index `uq_quotes_portal_folio ... WHERE portal_folio IS NOT NULL`
  - `create_table("quote_wizard_details", ...)` with named PG enum types and `UniqueConstraint("quote_id")`
  - `create_table("quote_wizard_documents", ...)`
  - RLS tenant policy for both new tables (mirror `quotes`/`quote_items` policy pattern per `docs/architecture/rls-multi-tenant.md`)
  - `downgrade()`: drop tables, drop index, drop column, drop enum types
- [x] 1.6 Migration smoke test: `alembic upgrade head` then `alembic downgrade -1` cleanly in test DB (verified manually + via pytest conftest auto-upgrade).
- [x] 1.7 **Living docs**: update `20-Arquitectura/ARQ-001-Decisiones-Core.md` with `Quote.portal_folio`, `quote_wizard_details`, `quote_wizard_documents` (frontmatter `status: active`, update `created`/module fields as needed).

*Depends on: Phase 0 (0.1). Parallel-safe with: nothing (foundation for all backend work). Blocks: Phase 2, 3, 4.*

---

## Phase 2 — Portal gate client (PR #2)

- [x] 2.1 New module `modules/portal_gate/client.py`: `PortalFolioStatus` enum (`ELIGIBLE`/`NOT_ELIGIBLE`/`UNAVAILABLE`), `PortalGateError`, `PortalUnavailableError`, `validate_folio(folio) -> PortalFolioStatus` per design §3 (httpx.Client, timeout 5s/connect 3s, retry only on timeout/ConnectError/5xx, no retry on 403/404).
- [x] 2.2 Add config settings to `core/config.py`: `PORTAL_API_BASE_URL`, `PORTAL_RETRY_ATTEMPTS` (default 3), `PORTAL_API_KEY` (optional header hook).
- [x] 2.3 pytest: `test_portal_gate_client.py` — mock httpx transport:
  - 200 + `quotation_in_progress` → `ELIGIBLE`
  - 200 + other status → `NOT_ELIGIBLE`
  - 404 → `NOT_ELIGIBLE`, no retry
  - 403 → `NOT_ELIGIBLE`, no retry
  - timeout on attempt 1, success on attempt 2 → `ELIGIBLE`, assert retry happened with backoff
  - timeout/5xx on all attempts (retries exhausted) → raises `PortalUnavailableError`

*Depends on: Phase 0 (0.3). Parallel-safe with: Phase 1 (no shared files). Blocks: Phase 3.*

---

## Phase 3 — Submit service + pricing correctness (PR #3)

- [x] 3.1 New `crm/schemas.py` DTOs: `PublicWizardItem`, `WizardServiceSelection`, `PublicQuoteRequestCreate` with all Pydantic field validators + `@model_validator` conditionals (RN-006, RN-007, RN-008, RN-009, RN-010, RN-011, RN-014, RN-017) per design §2.3.
- [x] 3.2 New `crm/public_service.py::create_public_quote_request(tenant_id, payload, db) -> Quote`:
  - `_duration_hours()` helper (returns `Decimal`)
  - correct pricing call per item: `calculate_price(space_id, duration_hours: Decimal, tenant_id, target_date: date, db)` — propagate `NoPricingRuleError`, no broad `except`, no caller-supplied fallback price
  - persistence order: `Lead` → `Quote(portal_folio=...)` → `QuoteItem[]` → `QuoteAdditionalService[]` → `QuoteWizardDetails` → `QuoteWizardDocuments[]` (if files provided) → `apply_soft_hold_for_quote(...)`
  - resolve HTTP mapping for `NoPricingRuleError` per task 0.2
  - **Note**: task 0.2 (409 vs 422 HTTP mapping) remains unresolved — out of scope for this PR (service layer only, no HTTP). `NoPricingRuleError` propagates uncaught; PR #4 (endpoints) owns the HTTP mapping decision.
- [x] 3.3 pytest: `test_public_service_pricing.py`:
  - seeded `PricingRule` → computed price equals `calculate_price(...)` result exactly (regression test proving this is NOT the `create_quote` broken pattern)
  - space with no pricing rule → `NoPricingRuleError` propagated, not silently defaulted
  - multi-item aggregate total == sum of per-item prices
- [x] 3.4 pytest: `test_public_service_atomicity.py`:
  - all items available → all rows persisted (Lead, Quote, QuoteItem×N, QuoteAdditionalService×N or 0, QuoteWizardDetails, QuoteWizardDocuments×N or 0), soft-hold applied
  - one item unavailable (pre-held by another quote) → `SlotNotAvailableError`, zero rows persisted for this attempt (verify via DB query after rollback)

*Depends on: Phase 1, Phase 0 (0.2). Parallel-safe with: Phase 2 (different files) but the endpoint phase needs both. Blocks: Phase 4.*

---

## Phase 4 — Gate + submit endpoints (PR #4)

- [x] 4.1 New `api/public.py` (or extend existing) — gate endpoint `POST /api/public/quote-requests/validate-folio`: format regex check first (422, no Portal call if invalid) → `portal_gate.validate_folio()` → 200 unlocked / 403 RN-003 / 503 PORTAL_UNAVAILABLE.
- [x] 4.2 Submit endpoint `POST /api/public/quote-requests` as **multipart/form-data**: `payload` part (JSON, parsed into `PublicQuoteRequestCreate`) + `files[]` part (0..N documents). Wire transaction boundary per design §4.2:
  1. Parse + validate `payload` JSON → 422 on failure, no DB touched
  2. Validate uploaded files against `MAX_KYC_FILE_BYTES` + existing MIME allowlist (reuse existing constants) → 422 on violation, no DB touched, no Portal call yet
  3. RN-004 revalidation via `portal_gate.validate_folio()` BEFORE opening the write tx → 403 / 503, nothing opened
  4. `with get_db_context(tenant_id=DEFAULT_TENANT_ID, role=None) as db:` → `check_group_availability()` pre-check → `create_public_quote_request()` (persists rows + saves file bytes to `WIZARD_DOCUMENTS_STORAGE_PATH`, storing `storage_key` in `QuoteWizardDocuments`) → `db.commit()`
  5. Catch `SlotNotAvailableError`/`IntegrityError`/`NoPricingRuleError`/`ValueError` → rollback → map to 409/422 per error table (design §4.4)
- [x] 4.3 Tenant resolution: both endpoints resolve `tenant_id` from `settings.DEFAULT_TENANT_ID`, no JWT/session dependency.
- [x] 4.4 Add settings: `WIZARD_DOCUMENTS_STORAGE_PATH` to `core/config.py`.
- [x] 4.5 pytest: `test_public_quote_gate.py`:
  - well-formed folio + Portal `quotation_in_progress` → 200 unlocked, no auth header required
  - malformed folio → 422 AND assert Portal client `validate_folio` NEVER called (spy/`assert_not_called`)
  - Portal 404/403/wrong-status → 403 RN-003 message
  - Portal timeout exhausted → 503 PORTAL_UNAVAILABLE (distinct from 403)
  - Portal timeout-then-success → 200, assert retry happened
  - **Note**: retry-then-success is covered in PR#2's `test_portal_gate_client.py` (per user's explicit scope note); PR#4's gate tests focus on the endpoint's HTTP mapping (200/403/503) using a mocked `validate_folio`.
- [x] 4.6 pytest: `test_public_quote_submit.py`:
  - happy path multi-item (3 items) + documents → 201; assert Quote.total == aggregate, 3 QuoteItems, QuoteWizardDetails row, QuoteWizardDocuments rows persisted with correct storage_key, portal_folio set, Lead created, NO User row
  - RN-004: eligible at gate, Portal reports not-eligible at submit-time revalidation → 403, zero rows persisted (query DB to confirm)
  - RN-004: Portal unavailable at submit-time revalidation → 503, zero rows persisted
  - multi-item atomic rollback: 1 of 3 items pre-held by another quote → 409 SLOT_UNAVAILABLE, zero rows for this attempt
  - duplicate folio replay → 409 DUPLICATE_FOLIO, no second Quote
  - conditional validation matrix (parametrized): tipo_evento=Otro w/o nombre (RN-008), sector=Otro w/o sector_otro (RN-009), como_conociste=Otro w/o detalle (RN-010), material_externo=true w/o detalle (RN-011), descripcion>300 words (RN-006), asistentes≤0 (RN-007), each legal acceptance false/missing (RN-014) → 422, zero rows
  - no-auth access: gate + submit succeed with no Authorization header
  - tenant resolution: persisted rows carry `tenant_id == DEFAULT_TENANT_ID`
  - multipart document persistence: valid MIME/size files persisted; invalid MIME/oversized file rejected with same existing validation behavior (RN-015), zero rows
  - **Result**: 23/23 new tests GREEN (`test_public_quote_gate.py` + `test_public_quote_submit.py`); PR#1–3 regression suite (`test_portal_gate_client.py`, `test_public_service_pricing.py`, `test_public_service_atomicity.py`, `test_public_catalog.py`) re-run GREEN, no regression introduced by this PR (pre-existing unrelated collection/DB-isolation failures in other test files confirmed present on the base branch too via `git stash` comparison).

*Depends on: Phase 2, Phase 3. Sequential — cannot start until both are merged/available.*

---

## Phase 5 — Notifications: best-effort confirmation email (PR #5, can bundle with Phase 4 if small enough)

- [x] 5.1 New Jinja template `notifications/templates/public_quote_confirmation.html` with recepción/revisión ≤24h hábiles copy.
- [x] 5.2 Wire best-effort email in the submit endpoint AFTER `db.commit()` (design §5): `try/except`, log failure, never fail the request, `email_sent` reflected in response. No `NotificationLog` write.
- [x] 5.3 pytest: `test_public_quote_email.py`:
  - `send_email` mocked to raise → submit still 201, `email_sent=false`, failure logged, NO `NotificationLog` row written
  - `send_email` succeeds → 201, `email_sent=true`

*Depends on: Phase 4 (submit endpoint must exist). Can be folded into PR #4 if the reviewer budget allows; kept separate here for review-size control.*

---

## Phase 6 — Frontend: middleware fix + folio gate screen (PR #6)

- [x] 6.1 `middleware/auth-middleware.ts` — extend `isPublicPage` to include `request.nextUrl.pathname.startsWith('/solicitud')`.
- [x] 6.2 New route group `app/(public-wizard)/solicitud/page.tsx` — folio gate screen: input + validate call to `POST /api/public/quote-requests/validate-folio`, handles 200 unlocked / 403 RN-003 message / 503 Portal-unavailable message.
  - Also handles 422 invalid-format distinctly (server-authoritative; client regex is a UX hint only per RN-017).
- [x] 6.3 New Zustand store `features/quote-wizard/store/quote-wizard.store.ts` per design §6.3 (gate + step 1–5 state, `currentStep`, actions).
  - Exposed via `features/quote-wizard/index.ts` public barrel (project ESLint `no-restricted-imports` rule requires feature access through the index, not deep paths).
- [x] 6.4 e2e/Playwright (if in test scope): anonymous `/solicitud` is NOT redirected to `/login`.
  - `tests/e2e/solicitud-gate.spec.ts` written; runs from the HOST (Playwright browsers cannot run in the Alpine/musl frontend container) — not executed in this apply batch, only lint+tsc verified in-container.

*Depends on: Phase 4 (gate endpoint contract). Parallel-safe with Phase 5.*

---

## Phase 6b — Public price-preview endpoint (PR #6b, gap found during Phase 7 planning)

- [x] 6b.1 `POST /api/public/quote-requests/price-preview` (public, no auth) in `src/backend/app/api/public.py` — accepts a list of `{space_id, fecha, hora_inicio, hora_fin}` items, resolves `tenant_id = settings.DEFAULT_TENANT_ID`, calls `pricing.services.calculate_price` per item with the CORRECT types (reusing `crm/public_service.py::_duration_hours`), returns per-item price + spaces-only aggregate `total`. `NoPricingRuleError` -> 422 `NO_PRICING_RULE` (consistent with submit, design §4.4). Advisory only — submit always recomputes the authoritative price server-side.
- [x] 6b.2 `tests/test_public_price_preview.py` — single item matches `calculate_price` result; multi-item aggregate == sum; space without a `PricingRule` -> 422 (not a silent default); no auth header required. Confirmed no regression in `test_public_quote_gate.py` / `test_public_quote_submit.py`.

**Why this was needed:** design §6.6 anticipated "a small public pricing-preview endpoint if needed" for Step 2 of the public wizard, which must display `cotizacionCalculada` to an ANONYMOUS user before submit. The existing `POST /quotes/calculate` and `/pricing-rules` both require JWT (`require_tenant`), so an anonymous client could not compute a price preview — this PR fills that gap.

*Depends on: Phase 4 (`calculate_price` correct-types pattern + `NoPricingRuleError` mapping). Feeds Phase 6 Step 2 (design §6.4/§6.6).*

---

## Phase 7 — Frontend: wizard steps 1–5 (PR #7, likely split further if >400 lines — see forecast)

- [x] 7.1 `app/(public-wizard)/solicitud/wizard/page.tsx` — step-driven client page reading `currentStep` from the store.
  - PR #7a: implemented with step indicator (1..5), Next/Back nav gated by per-step client validity, and a redirect-to-`/solicitud` guard when `folioUnlocked` is false.
- [x] 7.2 Step 1 component (Evento): fields + client guards (RN-006/007/008 UX mirrors).
  - PR #7a: `features/quote-wizard/components/StepEvento.tsx` + `features/quote-wizard/validation.ts::isStepEventoValid` + `features/quote-wizard/constants.ts` (frozen enum values).
- [x] 7.3 Step 2 component (Espacio/fecha/cotización, multi-item): add/remove item blocks, availability + pricing preview call (design §6.6), `cotizacionCalculada` display.
  - PR #7a: `features/quote-wizard/components/StepEspacio.tsx` — calls `POST /spaces/check-availability` then `POST /public/quote-requests/price-preview` per item; aggregate preliminary total; graceful unavailable/422 handling.
- [x] 7.4 Step 3 component (Solicitante y documentos): fields + conditional guards (RN-009/010) + `DocumentUpload.tsx` extracted from `booking/confirm/page.tsx` (RN-015, same MIME/size messaging, no rule change), wired to `store.documents`.
  - PR #7b: `features/quote-wizard/components/StepSolicitante.tsx` + `DocumentUpload.tsx` (flat `documents.adjuntos` File[] bucket — the wizard has no per-type document catalog, unlike `booking/confirm`'s KYC flow). Fixed oficio/gobierno informational note per REQ §4.4.
- [x] 7.5 Step 4 component (Servicios y montaje): `servicios_apoyo` multi-select, `montaje_requerido`, conditional `material_externo_detalle` guard (RN-011).
  - PR #7b: `features/quote-wizard/components/StepServicios.tsx`. `servicios_apoyo` catalog fetch is best-effort against `/additional-services` (**no such public endpoint exists yet** — degrades gracefully to "no hay servicios disponibles" without blocking the step; `servicios_apoyo` is optional `[]` in `PublicQuoteRequestCreate`). Flagged as a follow-up risk, not a regression — out of this PR's frontend-only scope.
- [x] 7.6 Step 5 component (Resumen, aceptaciones, envío): summary render, both legal-acceptance checkboxes (RN-014) with links to `LEGAL_REGLAMENTO_URL`/`LEGAL_AVISO_PRIVACIDAD_URL`, submit disabled until both true, calls `POST /api/public/quote-requests` as multipart.
  - PR #7b: `features/quote-wizard/components/StepResumen.tsx` — full read-only summary, multipart `FormData` (`payload` JSON + `files`), distinct inline error copy for 403/409 (SLOT_UNAVAILABLE/DUPLICATE_FOLIO)/422/503.
- [x] 7.7 `app/(public-wizard)/solicitud/confirmacion/page.tsx` — success screen (≤24h hábiles message), shown regardless of `email_sent`.
  - PR #7b: renders regardless of `email_sent` (subtle note only if false); resets the wizard store on mount.
- [x] 7.8 e2e/Playwright (if in test scope): submit button stays disabled until both acceptance checkboxes are true.
  - PR #7b: `tests/e2e/solicitud-wizard-submit.spec.ts` written; host-only (not run in-container), lint+tsc verified in-container.

*Depends on: Phase 6 (store + gate screen), Phase 4/5 (submit contract + email confirmation copy). Sequential internally (steps share the store) but each step file is an independent commit/reviewable unit within the PR — consider splitting into PR #7a (steps 1-2) / #7b (steps 3-5 + confirmation) per Review Workload Forecast below.*

---

## Phase 8 — Config settings consolidation + legal URLs (small, bundle into Phase 1 or 4 PR)

- [x] 8.1 Add `LEGAL_REGLAMENTO_URL`, `LEGAL_AVISO_PRIVACIDAD_URL` placeholder settings to `core/config.py`.
  - PR #7b: added to `src/backend/app/core/config.py` (were listed in design §7 but not yet in the file).
- [x] 8.2 Add matching `NEXT_PUBLIC_LEGAL_*` frontend env placeholders, referenced by Step 5 checkboxes.
  - PR #7b: `features/quote-wizard/constants.ts` — `LEGAL_REGLAMENTO_URL` / `LEGAL_AVISO_PRIVACIDAD_URL` read `process.env.NEXT_PUBLIC_LEGAL_REGLAMENTO_URL` / `NEXT_PUBLIC_LEGAL_AVISO_PRIVACIDAD_URL` with matching fallback defaults.

*Depends on: none functionally; bundle wherever convenient (recommend folding into Phase 2 or Phase 6 commit).*

---

## Phase 9 — Living documentation (mandatory, do continuously + final pass)

- [ ] 9.1 `30-API/` — new file documenting `/api/public/quote-requests/validate-folio` and `/api/public/quote-requests` (method, payload incl. multipart shape, responses, status codes) per CLAUDE.md convention (frontmatter `id: API-0XX`, `status: active`).
- [ ] 9.2 `20-Arquitectura/ARQ-001-Decisiones-Core.md` — confirm/finalize entries for `Quote.portal_folio`, `quote_wizard_details`, `quote_wizard_documents` (should already be partially done in Phase 1; verify completeness once endpoints/service land).
- [ ] 9.3 `10-Requerimientos/REQ-012-Solicitud-Cotizacion-Folio-Portal.md` — tick DoD checkboxes (`[ ]` → `[x]`) for every RN satisfied by this change.
- [ ] 9.4 `50-Bitacora/BIT-XXX-Estatus-REQ-012.md` — new bitácora entry: what was implemented, local smoke-test results, pending items (e.g. RISK-1 enum freeze confirmation, deferred Portal state sync-back).
- [ ] 9.5 `40-Ejecucion/TSK-XXX-*.md` — set `status: done` in frontmatter for any corresponding execution task files.

*Depends on: relevant phase completion; do incrementally per phase, finalize at the end. Non-negotiable per CLAUDE.md.*

---

## Phase 10 — Correction: `servicios_apoyo` fixed enum, not catalog (PR #8)

**Why:** REQ-012 §4.5 defines `servicios_apoyo` as a FIXED closed multi-enum of 8 labels — NOT dynamic catalog items. PR #3/#4/#7b wrongly modeled it as `{service_id: uuid, quantity}` against the `AdditionalService` catalog (there is no public catalog-listing endpoint and the 8 services aren't catalog rows).

- [x] 10.1 Backend: add `ServicioApoyo` enum (8 frozen values) to `crm/models.py`; add `quote_wizard_details.servicios_apoyo` (`text[]`) via additive migration `r7s8t9u0v1w2`. Change `PublicQuoteRequestCreate.servicios_apoyo` to `list[ServicioApoyo]`; remove `WizardServiceSelection`. Remove the `QuoteAdditionalService` persistence loop from `create_public_quote_request` — servicios are not priced.
- [x] 10.2 Backend tests: `TestSubmitServiciosApoyo` in `test_public_quote_submit.py` — selected servicios persist verbatim on `quote_wizard_details`; invalid value → 422, zero rows. Full regression suite (Phase 1-5 tests) re-run green.
- [x] 10.3 Frontend: `constants.ts::SERVICIOS_APOYO` (fixed labels), `quote-wizard.store.ts` (`serviciosApoyo: string[]` + `toggleServicioApoyo`, replaces `ServiceSelection`), `StepServicios.tsx` (renders fixed list, no `/additional-services` fetch), `StepResumen.tsx` (submit payload sends `servicios_apoyo: string[]`). `tsc`/`eslint` clean.
- [x] 10.4 Living docs: `API-025-PublicQuoteRequests.md`, `ARQ-001-Decisiones-Core.md` §15.6, `BIT-012-Estatus-REQ-012.md` updated.

*Depends on: Phase 4 (submit endpoint), Phase 7 (Step 4/5 frontend). Branch `feat/qrf-08-servicios-enum`, child of `feat/qrf-07b-wizard-steps345` (feature-branch-chain).*

---

## Task → Requirement traceability

| Task group | RN covered |
| :-- | :-- |
| 1.5 (migration), 3.2 (portal_folio persist) | RN-013 |
| 2.1–2.3 | RN-001, RN-002, resilience req |
| 4.1, 4.5 | RN-001, RN-002, RN-003, RN-017 |
| 4.2, 4.6 (RN-004 tests) | RN-004 |
| 3.1 (`@model_validator`), 4.6 (matrix) | RN-005, RN-006, RN-007, RN-008, RN-009, RN-010, RN-011, RN-014 |
| 3.2, 3.3, 3.4, 4.6 | RN-012 |
| 4.2, 4.6 (multipart/document tests) | RN-015 |
| 5.1–5.3 | RN-016 |
| 4.3, 4.6 (tenant/no-auth tests) | RN-002 (config), public access |
| 3.1 (`folio` regex) | RN-017 |

---

## Review Workload Forecast

**Estimated changed lines (additions + deletions), by phase:**

| Phase | Est. lines | Notes |
| :-- | --: | :-- |
| 0 — Risk confirmations | ~0 (docs/notes only) | |
| 1 — Data model + migration + living docs | ~350 | 5 enums, 2 new models, 1 migration, ARQ-001 update |
| 2 — Portal gate client + tests | ~300 | client + config + 6 test cases |
| 3 — Submit service + pricing + tests | ~400 | schemas + service + 2 test files |
| 4 — Gate + submit endpoints + tests | ~450 | 2 endpoints, multipart handling, 2 large test files |
| 5 — Email | ~120 | template + wiring + tests |
| 6 — Middleware + gate screen + store | ~280 | |
| 7 — Wizard steps 1–5 + confirmation | ~650 | 5 step components + document upload extraction |
| 8 — Config/legal URLs | ~30 | bundle elsewhere |
| 9 — Living docs (Obsidian) | ~150 (outside repo diff, tracked separately) | not counted in repo PR line budget |

**Total estimated repo diff: ~2,580 lines** (excluding Obsidian docs, which live outside this repo).

**400-line budget risk: High.** Every phase except 0, 5, 8 individually exceeds or approaches 400 lines; the total is ~6.5x the single-PR budget.

**Chained PRs recommended: Yes.**

**Decision needed before apply: Yes** — confirm chain strategy (`stacked-to-main` vs `feature-branch-chain`) per `ask-on-risk` delivery strategy before `sdd-apply` begins.

**Suggested PR slicing (dependency-ordered, chained-pr skill applied):**

```
PR #1: Phase 1 (data model + migration + ARQ-001 docs)                📍 (start)
  │
  ├─→ PR #2: Phase 2 (Portal gate client) ── parallel-safe with PR #1
  │
  └─→ PR #3: Phase 3 (submit service + pricing, depends on PR #1)
        │
        └─→ PR #4: Phase 4 (gate + submit endpoints, depends on PR #2 + PR #3)
              │
              ├─→ PR #5: Phase 5 (email, depends on PR #4) — or fold into PR #4 if reviewer accepts ~570 combined lines under size:exception
              │
              └─→ PR #6: Phase 6 (middleware + gate screen + store, depends on PR #4 contract)
                    │
                    └─→ PR #7a: Phase 7 steps 1–2 (depends on PR #6)
                          │
                          └─→ PR #7b: Phase 7 steps 3–5 + confirmation (depends on PR #7a, ships Phase 8 legal-URL frontend env)
```

Each PR carries Phase 9 living-doc updates relevant to what it introduces (API doc lands with PR #4, ARQ-001 lands with PR #1, DoD/bitácora finalize with the last PR).

**Recommended chain strategy:** `feature-branch-chain` — this feature must integrate fully (gate + wizard + submit) before it is usable in `main`; a draft tracker branch collecting PR #1–#7b, merging to `main` only once the full flow is reviewable end-to-end, avoids landing a half-built public wizard on `main`. `stacked-to-main` is viable only if the team accepts an incomplete-but-inert public route living on `main` between merges (mitigated by the middleware whitelist only being added in PR #6, so `/solicitud` stays inaccessible/unlisted until then).

**Final ask (per `ask-on-risk`):** confirm PR slicing + chain strategy with the user before `sdd-apply` starts Phase 1.
