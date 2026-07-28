# Proposal: Solicitud de Cotización mediante Folio de BLOQUE Portal (`quote-request-folio`)

**Source requirement:** REQ-012 (`10-Requerimientos/REQ-012-Solicitud-Cotizacion-Folio-Portal.md`)
**Change name:** `quote-request-folio`
**Module:** `crm` (extends `Lead → Quote → QuoteItem`), plus `inventory`, `pricing`, `notifications`, `api/public`, and frontend public wizard.

---

## Why

Today Hub has no gated, self-service path for a prospect to turn a qualified BLOQUE Portal lead (`BCE-…`) into a Hub quote request. Quotes are created only through the internal COMMERCIAL flow (`crm/services.py::create_quote`, which needs a pre-existing `Lead` and staff context). The consequences:

- **Broken funnel between Portal and Hub.** A lead qualified in Portal ("Cotización en proceso" / `quotation_in_progress`) has no way to continue into Hub without manual re-keying by the commercial team.
- **Unqualified / noise cotizaciones.** Without a folio gate, anything reaching the quote path is unfiltered. REQ-012 requires that only folios in `quotation_in_progress` may start the wizard (RN-001/RN-002/RN-003).
- **No cross-system traceability.** There is no `portal_folio` link on `Quote`, so a submitted request cannot be audited back to its originating Portal lead (RN-013 / HU-08).

**Business value:** unify the Portal → Hub commercial funnel, block unqualified requests at the gate, and guarantee `BCE-…` ↔ Hub `Quote` traceability. Success = a solicitante with a valid folio completes a public 5-step wizard, the request persists as a `Quote` linked to its folio with correctly-computed pricing, and a confirmation email is attempted — with zero login and zero customer account created.

---

## What Changes

A new **public** (no-login) request flow, gated by folio, that reuses Hub's existing availability, pricing, and quote-persistence machinery.

- **Folio gate (public).** New public endpoint(s) under `/api/public/*` that accept a `BCE-…` folio, validate its format (RN-017), call the BLOQUE Portal API to confirm status is `quotation_in_progress` (RN-002), and either unlock the wizard (`200`) or block it with a distinct reason (RN-003). The folio is the ONLY credential — no JWT, no customer user.
- **5-step wizard (public frontend).** New public route group with a Zustand-backed client state machine holding all step data until an atomic submit:
  - **Step 1 — Evento:** `tipo_evento` (enum), `nombre_evento` (required only if `tipo_evento = Otro`, RN-008), `caracter_evento` (enum), `descripcion_evento` (text, max 300 words, RN-006), `asistentes_estimados` (int > 0, RN-007), `habra_prensa` (bool).
  - **Step 2 — Espacio, fecha y cotización (MULTI-space / multi-day from MVP):** for each selected block — `space_id`, `fecha`, `hora_inicio`, `hora_fin` — validate availability via `inventory.check_single_availability` / `check_group_availability`, and compute `cotizacion_calculada` via `pricing.calculate_price` / `get_quote_for_space` with **correct types** (`target_date: date`, `duration_hours: Decimal`). Aggregate total across all items (RN-012). Each block becomes a `QuoteItem`; the whole submission is ONE `Quote` (1:1 folio↔Quote, 1:N Quote↔items).
  - **Step 3 — Solicitante y documentos:** `nombre_completo`, `cargo_puesto`, `institucion_organizacion`, `sector` (enum) + `sector_otro` (required if `Otro`, RN-009), `correo_institucional`, `telefono_contacto`, `responsable_sitio_nombre`/`responsable_sitio_telefono` (optional), `como_conociste_bloque` (enum) + `como_conociste_otro` (required if `Otro`, RN-010), plus document upload adapted from the inline block in `app/(customer)/booking/confirm/page.tsx` with NO functional change to MIME/size/versioning rules (RN-015). Shows the fixed government-oficio informational note.
  - **Step 4 — Servicios y montaje:** `servicios_apoyo` (multi-select → existing `QuoteAdditionalService` + `AdditionalService` catalog), `montaje_requerido` (enum, required), `requerimientos_especiales` (text), `material_externo` (bool) + `material_externo_detalle` (required if `Sí`, RN-011).
  - **Step 5 — Resumen, aceptaciones y envío:** full summary incl. computed quote; submit stays disabled until BOTH legal acceptances are `true` (`acepta_info_correcta_autorizacion`, `acepta_reglamento_y_aviso_privacidad`, RN-014).
- **Atomic submit with folio revalidation (RN-004).** On submit, Hub re-calls Portal; if status is no longer `quotation_in_progress`, the request is rejected and NOTHING is persisted. On success, Hub persists a `Lead` (requester data, NOT a user account) + `Quote` (with `portal_folio`) + `QuoteItem[]` + `QuoteAdditionalService[]` + a new `quote_wizard_details` adjunct row, applying the existing inventory soft-hold.
- **Server-side validation.** All required and conditional rules (RN-005…RN-011, RN-014, RN-017) enforced on the backend, not only in the UI.
- **Confirmation email (RN-016), best-effort non-blocking.** After the Quote is persisted, attempt a synchronous confirmation email to `correo_institucional` inside a `try/except` that does NOT fail the submit; on failure the request still succeeds, the failure is logged, and the user sees the confirmation screen (recepción / revisión ≤ 24 h hábiles). Does NOT use `NotificationLog` (it FKs reservations, not quotes).
- **Portal client resilience.** The httpx wrapper retries 2–3 times with short backoff on timeout/5xx and surfaces a distinct "Portal unavailable" error separate from "folio invalid / wrong status".
- **Middleware whitelist.** Add the new public wizard route(s) to `isPublicPage` in `src/frontend/middleware/auth-middleware.ts` (currently only `/` and `/catalog`) so anonymous access is not redirected to `/login`.
- **Config.** Add `PORTAL_API_BASE_URL` setting for the Portal gate; resolve `tenant_id` (sede) from configuration via existing `settings.DEFAULT_TENANT_ID` / `optional_tenant_for_catalog`.

---

## Scope

### In scope
- Public folio gate endpoint(s) + Portal validation client (httpx, with retry/backoff).
- Public 5-step wizard frontend (new route group + Zustand store), including the middleware whitelist fix.
- **Multi-space / multi-day submission from MVP** (several `QuoteItem` per submit, aggregate total).
- Backend atomic submit: `Lead` (requester data only) + `Quote` (`portal_folio`) + `QuoteItem[]` + `QuoteAdditionalService[]` + new `quote_wizard_details` adjunct table (1:1 with Quote) + Alembic migration.
- Correct reuse of `inventory` availability and `pricing` (correctly-typed calls) — explicitly NOT copying the broken `create_quote` pricing call.
- Confirmation email (RN-016) as best-effort non-blocking.
- Server-side validation of all obligatory/conditional rules.
- `PORTAL_API_BASE_URL` config; sede via `DEFAULT_TENANT_ID`.

### Out of scope
- **Portal state sync-back** after submit (e.g. moving the Portal lead to "Cotización enviada") — deferred.
- **`lead_prefill`** from Portal to hydrate Step 3 — NOT used in MVP. **(Later delivered by `req-013-portal-hmac`.)**
- Creating a `CUSTOMER` user / login — the wizard is 100% public; requester is data on the Lead.
- Redefining the internal lead/quote state machine beyond adding the folio link.
- FEA / contract signing (REQ-005), SEMI_DIRECT reservations/pase de caja (REQ-004), KYC document rule changes (REQ-010).
- Final legal copy for Reglamento / Aviso de Privacidad.
- Mobile / WhatsApp channels.

### Assumptions (stated, not blockers)
- **Legal copy URLs** (Reglamento / Aviso de Privacidad) are provided via env placeholder settings until legal supplies the canonical documents; the checkboxes link to those configurable URLs.
- **Portal gate auth** on the internal network (API key/HMAC) is assumed not required for MVP; if Portal requires it, it is added to the client wrapper as a config-driven header without changing the flow. **(Archive note 2026-07-28 — this assumption proved FALSE. Portal requires mandatory HMAC-SHA256 signing. Tracked as RISK-4 and closed by `req-013-portal-hmac`; the change was larger than "a config-driven header" because the route, the auth scheme and the status field all changed together.)**
- `status_post_envio` uses the existing default initial Quote status for a newly submitted quote (no new state introduced beyond the folio link).

---

## Impact

### Backend
- `src/backend/app/api/public.py` — new gate + wizard-submit endpoints under `/api/public/*`.
- `src/backend/app/core/config.py` — add `PORTAL_API_BASE_URL`; confirm `DEFAULT_TENANT_ID` as sede source; add legal-URL placeholder settings.
- `src/backend/app/modules/crm/{models,services,schemas}.py` — add `portal_folio` (unique, indexed) to `Quote`; new `quote_wizard_details` 1:1 adjunct model; new public-submit service that calls pricing/availability correctly (does NOT reuse the buggy `create_quote` pricing call).
- New **Portal gate HTTP client** (thin httpx wrapper: `validate_folio(folio) -> PortalFolioStatus`, retry 2–3× + backoff, distinct error taxonomy).
- `src/backend/app/modules/inventory/` and `pricing/` — reused unchanged (correctly-typed calls).
- `src/backend/app/modules/notifications/` — new confirmation email (Jinja template + send), best-effort non-blocking, no `NotificationLog`.
- `src/backend/alembic/versions/` — additive migration: `quotes.portal_folio` + `quote_wizard_details` table.

### Frontend
- New public route group + pages for the 5-step wizard + folio gate screen.
- New Zustand store for wizard state (controlled inputs; no RHF/Zod precedent, stick to existing patterns unless the team opts in).
- Document-upload block adapted from `app/(customer)/booking/confirm/page.tsx` (RN-015).
- `src/frontend/middleware/auth-middleware.ts` — add wizard route(s) to `isPublicPage`.

### Data model
- `Quote.portal_folio` (unique, indexed) — the Portal↔Hub traceability link.
- New `quote_wizard_details` (quote_id FK unique) holding Step 1/3/4 wizard-specific fields + legal acceptances; `servicios_apoyo` reuses `QuoteAdditionalService`.

### Living documentation (mandatory at apply time)
- `30-API/` — document new `/api/public/*` gate + submit endpoints.
- `20-Arquitectura/ARQ-001` — `Quote.portal_folio` field + `quote_wizard_details` table.
- Tick REQ-012 DoD checkboxes; add `50-Bitacora/` implementation log.

---

## REQ-012 Business Rules → Change mapping

| RN | Rule | Where addressed |
| :-- | :-- | :-- |
| RN-001 | Only `quotation_in_progress` folios may start | Gate endpoint checks Portal status before unlocking wizard |
| RN-002 | Pre-validate via Portal API | Portal gate client called before Step 1 |
| RN-003 | Block on invalid/other status | Gate returns distinct block reason + RN-003 message |
| RN-004 | Revalidate on submit | Submit re-calls Portal; reject + no persist if not `quotation_in_progress` |
| RN-005 | Required fields, client + server | Server-side validation on submit + client step guards |
| RN-006 | `descripcion_evento` ≤ 300 words | Client + server validation |
| RN-007 | `asistentes_estimados` > 0 integer | Client + server validation |
| RN-008 | `nombre_evento` required if `tipo_evento = Otro` | Conditional validation |
| RN-009 | `sector_otro` required if `sector = Otro` | Conditional validation |
| RN-010 | `como_conociste_otro` required if `Otro` | Conditional validation |
| RN-011 | `material_externo_detalle` required if `Sí` | Conditional validation |
| RN-012 | Reuse availability + pricing | `inventory.check_*_availability` + `pricing.calculate_price` (correct types) |
| RN-013 | Persisted request linked to folio | `Quote.portal_folio` (unique, indexed) |
| RN-014 | Both legal acceptances required to submit | Submit disabled until both true; enforced server-side |
| RN-015 | Documents unchanged | Reuse inline upload block from `booking/confirm/page.tsx` |
| RN-016 | Persist + email + confirmation screen | Atomic persist, best-effort non-blocking email, success screen (≤ 24 h hábiles) |
| RN-017 | Folio format `BCE-YYYYMMDD-HHMMSS-RRRR` | Format check before Portal call |

---

## Known critical findings baked in
- **Pricing bug:** `crm/services.py::create_quote` calls `get_quote_for_space` with wrong-typed args swallowed by a broad `except`, silently falling back to caller `precio`. The new submit path MUST call pricing with `target_date: date` + `duration_hours: Decimal` and must NOT copy this pattern. (Design phase to resolve the exact call.)
- **Middleware gap:** `isPublicPage` whitelists only `/` and `/catalog`; the wizard route(s) MUST be added or anonymous access breaks.
