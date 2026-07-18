# Exploration: REQ-012 Solicitud de Cotización mediante Folio de BLOQUE Portal (quote-request-folio)

## Current State

### CRM write path (`src/backend/app/modules/crm/`)
- `services.py::create_quote(tenant_id, lead_id, items, discount_pct, discount_amount, discount_justification, db)` is the single entry point that builds a `Quote` + `QuoteItem[]` and applies the inventory soft-hold atomically. It requires an existing `Lead` (looked up by `lead_id`); leads are created separately via `LeadCreate` (`name`, `email`, `phone`, `company`, `notes` — no extra fields).
- **BUG FOUND (relevant to RN-012 reuse):** inside `create_quote`, pricing is computed via `get_quote_for_space(db, tenant_id, it.space_id, start_time, end_time)` with two `datetime`s, but the real signature is `get_quote_for_space(db, tenant_id, space_id, target_date: date, duration_hours: Decimal) -> dict`. The call is wrapped in a broad `except (ValueError, Exception): calculated_price = Decimal(str(it.precio))`, so `create_quote` almost always silently falls back to the caller-supplied `precio` instead of computing dynamic pricing. The wizard's `cotizacion_calculada` step must call `pricing.services.calculate_price` / `get_quote_for_space` correctly (with `target_date: date` + `duration_hours: Decimal`), NOT copy this broken pattern — otherwise RN-012 is nominally satisfied but practically broken.
- `Quote` model has no `portal_folio` field. `Lead` has no extra fields. No adjunct "solicitud pública" table exists.
- `QuoteAdditionalService` (join table quote_id ↔ `additional_services.id`, quantity, calculated_price) models Step 4's `servicios_apoyo` naturally. It does NOT model `montaje_requerido` (single enum), `requerimientos_especiales` (text), or `material_externo`/`material_externo_detalle`.

### Availability (`app/modules/inventory/`)
- `router.py::check_availability` (`POST /spaces/check-availability`) and `check_availability_group` are ALREADY public-safe: they use `Depends(optional_tenant_for_catalog)` (not `require_tenant`). Service functions: `check_single_availability(space_id, fecha, hora_inicio, hora_fin, db, role)` and `check_group_availability(...)`. Correct reuse target for Step 2.
- `apply_soft_hold_for_quote(quote_id, slots, tenant_id, db)` is the atomic hold applied inside `create_quote` — reuse unchanged.

### Pricing (`app/modules/pricing/services.py`)
- `calculate_price(space_id, duration_hours: Decimal, tenant_id, target_date: date, db) -> PriceBreakdown` is the real engine. `get_quote_for_space(db, tenant_id, space_id, target_date, duration_hours) -> dict` wraps it. Use these correctly-typed calls for Step 2's `cotizacion_calculada`.

### Public endpoint pattern (`app/api/public.py`)
- Router prefix `/api`, tag `public`, mounted via `app.include_router(public_router)` (no `API_V1_PREFIX`, no JWT).
- `get_db_context(tenant_id=None, role="SUPERADMIN")` from `app/db/session.py` is the pattern for opening a DB session outside `Depends(get_db)`, with RLS `SET LOCAL` via `after_begin` listener. For tenant-scoped public writes, call with `tenant_id=<resolved sede>, role=None`.
- **Sede/tenant resolution for anonymous access already exists**: `app/dependencies/auth.py::optional_tenant_for_catalog` falls back to `settings.DEFAULT_TENANT_ID` or the first active tenant. This is exactly the "tenant_id resolved from CONFIGURATION" mechanism REQ-012 wants — reuse `DEFAULT_TENANT_ID`, don't invent a new setting.
- `app/core/config.py` has `DEFAULT_TENANT_ID: str | None`. No `PORTAL_API_BASE_URL` yet — only `PORTAL_BASE_URL: str = "https://portal.bloque.example"` (likely a display/link URL). A new `PORTAL_API_BASE_URL` setting must be added.

### Outbound HTTP
- `httpx>=0.27.0` is already a backend dependency but currently unused for outbound calls — no existing httpx client module to model after. New pattern (thin service wrapper recommended).

### Email/notifications (`app/modules/notifications/`)
- `email_service.py::send_email(to, subject, html_body, text_body=None, attachments=None)` supports `mock` (writes to `data/emails/`) and `smtp` via `settings.EMAIL_PROVIDER`.
- `tasks.py` — Celery tasks load context inside `get_db_context(...)`, render Jinja templates via `notifications/templating.py::render(...)`, then call `send_email`. Templates in `app/modules/notifications/templates/*.html`. This Celery-task + Jinja-template pattern is the reuse target for RN-016.
- `NotificationLog` (dedup log) has `reservation_id` FK to `reservations`, not `quotes` — not directly reusable for a Quote-based email. Simplest: skip `NotificationLog`, fire-and-forget the Celery task (single one-shot email at submit).

### Frontend (`src/frontend/`)
- No existing 5-step wizard. No React Hook Form, no Zod. State pattern is **Zustand** (`features/booking/store/event-cart.store.ts`) + `useSWR` for GET + Axios `apiClient` (`lib/http/apiClient.ts`, `baseURL: NEXT_PUBLIC_API_URL || '/api'`) for mutations — plain controlled inputs.
- Closest analog is `app/(customer)/booking/confirm/page.tsx` — a single (not stepped) form combining cotización table + event data + contact + inline document upload, POSTing multipart `FormData`. **Document upload here is NOT a separate reusable component** — inlined in this page. `features/evidence/components/EvidenceUploader.tsx` is a different-purpose uploader (post-booking evidence). RN-015 should extract/adapt the inline block from `booking/confirm/page.tsx`.
- Routing: Next.js App Router with route groups. **Critical:** `isPublicPage` in `middleware/auth-middleware.ts` only whitelists `/` and `/catalog`. Any new public wizard route will be redirected to `/login` unless added to that whitelist. `NEXT_PUBLIC_BASE_PATH` respected via `redirectUrl()`.

### DB migrations
- Alembic, versions in `src/backend/alembic/versions/`. Adding `portal_folio` and new columns/adjunct table is a standard additive migration.

### Additional services & montaje (`app/modules/catalog/models.py`)
- `AdditionalService` + `QuoteAdditionalService` cover `servicios_apoyo`. New fields needed for `montaje_requerido`, `requerimientos_especiales`, `material_externo`/`material_externo_detalle`.

## Affected Areas
- `src/backend/app/api/public.py` — gate endpoint(s) + wizard submit under `/api/public/*`.
- `src/backend/app/core/config.py` — add `PORTAL_API_BASE_URL`; confirm `DEFAULT_TENANT_ID` as sede source.
- `src/backend/app/modules/crm/{models,services,schemas}.py` — `portal_folio` on Quote + adjunct table; use pricing correctly.
- `src/backend/app/modules/inventory/` and `pricing/` — reuse as-is.
- `src/backend/app/modules/notifications/` — new Celery task + Jinja template for RN-016.
- New Portal gate HTTP client (httpx) — thin wrapper.
- `src/backend/alembic/versions/` — new migration(s).
- `src/frontend/middleware/auth-middleware.ts` — add wizard route(s) to `isPublicPage`.
- `src/frontend/app/(customer)/booking/confirm/page.tsx` — source of doc-upload block for Step 3.
- New frontend route group/pages for the wizard + new Zustand store.

## Approaches (recommendations)

**A. `portal_folio` placement → on `Quote`** (unique, indexed). Write path is Quote-centric, RN-004 revalidation is a Quote-submit check, folio↔submission is 1:1 in MVP. Lead reachable via `quote.lead_id`.

**B. Multi-step persistence → atomic submit at Step 5**, state held client-side (Zustand). Matches `create_quote`'s all-or-nothing transaction and `booking/confirm/page.tsx`'s single-POST pattern. No orphaned partial records.

**C. Extra fields (Step 1/3/4) → new 1:1 adjunct table** (`quote_wizard_details`, `quote_id` FK unique) for all wizard-specific fields. Keeps `quotes`/`leads` clean for the internal COMMERCIAL flow. `servicios_apoyo` keeps using `QuoteAdditionalService`.

**D. Portal gate client → thin service wrapper, called synchronously** (`validate_folio(folio) -> PortalFolioStatus`). RN-002/RN-004 are must-block-and-wait. `httpx.Client(timeout=~5s)`, fail fast, map timeout/5xx to a distinct "Portal unavailable" error separate from "not found/wrong status".

## Risks
- **Pricing call bug** in `create_quote` — do not copy the broken `get_quote_for_space` call; call pricing with correct `date`+`Decimal` types.
- **Middleware whitelist miss** — must add the new public route to `isPublicPage` or anonymous access breaks.
- **Portal gate timeout/retry policy** is Pendiente de Confirmación (§11) — product decision on UX copy + retry on 5xx/timeout.
- **NotificationLog mismatch** — recommend skip logging, fire-and-forget Celery task.
- **No RHF/Zod precedent** — stick to Zustand + controlled inputs unless team wants to introduce validation tooling.
- Remaining §11 Pendientes: legal copy URLs, Portal state-sync (out of scope), multi-slot MVP boundary (assumed 1 space/1 slot).

## Ready for Proposal
Yes. Validate the four defaults (folio placement, persistence, extra-fields storage, gate client) and raise Portal timeout/retry UX copy + legal URLs as product questions during the proposal round.
