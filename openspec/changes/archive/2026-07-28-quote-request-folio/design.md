# Technical Design: Solicitud de Cotización mediante Folio de BLOQUE Portal (`quote-request-folio`)

**Source:** REQ-012, proposal + spec under `openspec/changes/quote-request-folio/`
**Module:** `crm` (extends `Lead → Quote → QuoteItem`), `inventory`, `pricing`, `notifications`, `api/public`, frontend public wizard.
**Status:** Design (architecture-level HOW). Task breakdown is deferred to `sdd-tasks`.

This design aligns to the 18 requirements in `spec.md`. Verified against on-disk code: `crm/{models,services,schemas}.py`, `pricing/services.py`, `inventory/services.py`, `api/public.py`, `db/session.py`, `core/config.py`, `middleware/auth-middleware.ts`, `booking/confirm/page.tsx`.

---

## 0. Architecture approach

**Pattern:** vertical slice on top of the existing modular-monolith. The public wizard is a thin, read-mostly gate + a single atomic write path that **reuses** the internal `inventory` and `pricing` engines with correct types. No new form library, no new auth surface, no user account.

**Layering (Screaming/Hexagonal-ish, matching repo conventions):**
- `api/public.py` — transport (FastAPI router, no JWT). Owns HTTP status mapping and the transaction boundary via `get_db_context`.
- `modules/crm/public_service.py` (NEW) — application service: `create_public_quote_request(...)`. Orchestrates validation → availability → pricing → persistence → soft-hold. Pure domain logic, receives an open `Session`.
- `modules/portal_gate/` (NEW) — outbound adapter: `validate_folio(folio) -> PortalFolioStatus`. Thin httpx wrapper, retry/backoff, error taxonomy. Isolated so it can be mocked in tests and swapped for auth-headers later.
- `modules/crm/schemas.py` — new Pydantic request/response DTOs with server-side validation (the source of truth for RN-005…RN-011, RN-014, RN-017).
- `modules/notifications/` — reuse `render()` + `send_email()` for the best-effort email.
- Frontend: new public route group `(public-wizard)` + one Zustand store, controlled inputs only.

**Boundary decisions:**
- The folio gate is **stateless** (no server session, no token issued on gate success). The wizard holds all state client-side; **RN-004 revalidation at submit** is the real security gate, so a forged "unlocked" client state cannot persist anything without passing revalidation + full server-side validation.
- `quote_wizard_details` is a 1:1 adjunct to keep `quotes`/`leads` clean for the internal COMMERCIAL flow (which must not grow wizard-only columns).

---

## 1. Data model

### 1.1 New enums (Python `str, enum.Enum` in `crm/models.py`)

Mirror the existing enum style (`QuoteStatus`). Values are stored as the enum member value. Use `values_callable=lambda x: [e.value for e in x]` on the SQLAlchemy `Enum(...)` column (as `Contract.status` already does) so DB values are the human strings, not the member names.

```python
class TipoEvento(str, enum.Enum):
    CONFERENCIA = "Conferencia"
    EXPOSICION = "Exposicion"
    REUNION = "Reunion"
    CAPACITACION = "Capacitacion"
    CULTURAL = "Cultural"
    OTRO = "Otro"

class CaracterEvento(str, enum.Enum):
    PUBLICO = "Publico"
    PRIVADO = "Privado"
    MIXTO = "Mixto"

class Sector(str, enum.Enum):
    PUBLICO = "Publico"
    PRIVADO = "Privado"
    ACADEMICO = "Academico"
    SOCIAL = "Social"
    OTRO = "Otro"

class ComoConociste(str, enum.Enum):
    REDES_SOCIALES = "RedesSociales"
    RECOMENDACION = "Recomendacion"
    BUSCADOR = "Buscador"
    EVENTO = "Evento"
    OTRO = "Otro"

class MontajeRequerido(str, enum.Enum):
    AUDITORIO = "Auditorio"
    ESCUELA = "Escuela"
    BANQUETE = "Banquete"
    MEDIA_LUNA = "MediaLuna"
    OTRO = "Otro"
    NINGUNO = "Ninguno"
```

> NOTE (ambiguity → RISK-1): REQ-012 does not fix the exact catalog values for these enums. Values above are a defensible default; `sdd-apply` MUST confirm against the REQ-012 field catalog / product before freezing, because enum values are hard to migrate later. The `Otro` member is REQUIRED in `TipoEvento`, `Sector`, `ComoConociste` (drives RN-008/009/010) and in `MontajeRequerido` (RN-011 is on `material_externo`, not montaje).

### 1.2 `Quote.portal_folio` (new column)

```python
# in Quote (crm/models.py)
portal_folio: Mapped[str | None] = mapped_column(
    String(32), nullable=True, unique=True, index=True
)
```

- **Type:** `String(32)` — folio `BCE-YYYYMMDD-HHMMSS-RRRR` is 24 chars; 32 gives headroom.
- **Nullable strategy:** `nullable=True`. Internal COMMERCIAL quotes (via `create_quote`) leave it `NULL`; wizard quotes set it. A **partial/filtered unique index** is the correct tool so multiple internal NULLs coexist while wizard folios stay unique:
  - Postgres allows multiple NULLs under a plain `UNIQUE` constraint already, so a simple `unique=True` is functionally sufficient. For clarity and to be explicit, the Alembic migration SHOULD create a **partial unique index**: `CREATE UNIQUE INDEX uq_quotes_portal_folio ON quotes (portal_folio) WHERE portal_folio IS NOT NULL;` and NOT declare `unique=True` inline (to avoid a redundant total unique index). Keep `index=True` semantics via the partial index.
- **Uniqueness → RN-013 replay protection.** A duplicate submit for the same folio hits the unique index → surfaced as HTTP 409 (see §4.4).

### 1.3 `quote_wizard_details` (new 1:1 adjunct table)

```python
class QuoteWizardDetails(Base):
    __tablename__ = "quote_wizard_details"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False, unique=True,   # enforces 1:1
    )

    # --- Step 1: Evento ---
    tipo_evento: Mapped[TipoEvento] = mapped_column(
        Enum(TipoEvento, values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    nombre_evento: Mapped[str | None] = mapped_column(String(255), nullable=True)  # required iff tipo_evento==Otro (RN-008)
    caracter_evento: Mapped[CaracterEvento] = mapped_column(
        Enum(CaracterEvento, values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    descripcion_evento: Mapped[str | None] = mapped_column(Text, nullable=True)  # <=300 words (RN-006)
    asistentes_estimados: Mapped[int] = mapped_column(Integer, nullable=False)  # >0 (RN-007)
    habra_prensa: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # --- Step 3: Solicitante ---
    nombre_completo: Mapped[str] = mapped_column(String(255), nullable=False)
    cargo_puesto: Mapped[str | None] = mapped_column(String(255), nullable=True)
    institucion_organizacion: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sector: Mapped[Sector] = mapped_column(
        Enum(Sector, values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    sector_otro: Mapped[str | None] = mapped_column(String(255), nullable=True)  # required iff sector==Otro (RN-009)
    correo_institucional: Mapped[str] = mapped_column(String(255), nullable=False)
    telefono_contacto: Mapped[str] = mapped_column(String(64), nullable=False)
    responsable_sitio_nombre: Mapped[str | None] = mapped_column(String(255), nullable=True)
    responsable_sitio_telefono: Mapped[str | None] = mapped_column(String(64), nullable=True)
    como_conociste_bloque: Mapped[ComoConociste] = mapped_column(
        Enum(ComoConociste, values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    como_conociste_otro: Mapped[str | None] = mapped_column(String(255), nullable=True)  # required iff Otro (RN-010)

    # --- Step 4: Servicios y montaje ---
    montaje_requerido: Mapped[MontajeRequerido] = mapped_column(
        Enum(MontajeRequerido, values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    requerimientos_especiales: Mapped[str | None] = mapped_column(Text, nullable=True)
    material_externo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    material_externo_detalle: Mapped[str | None] = mapped_column(Text, nullable=True)  # required iff material_externo (RN-011)

    # --- Step 5: Legal acceptances (RN-014) ---
    acepta_info_correcta_autorizacion: Mapped[bool] = mapped_column(Boolean, nullable=False)
    acepta_reglamento_y_aviso_privacidad: Mapped[bool] = mapped_column(Boolean, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    quote: Mapped["Quote"] = relationship("Quote", back_populates="wizard_details", uselist=False)
```

Add on `Quote`:
```python
wizard_details: Mapped["QuoteWizardDetails | None"] = relationship(
    "QuoteWizardDetails", back_populates="quote", uselist=False, cascade="all, delete-orphan"
)
```

- `servicios_apoyo` is NOT stored here — it reuses `QuoteAdditionalService` (already models quote_id ↔ additional_services.id + quantity + calculated_price).
- Legal acceptances stored as booleans for audit trail (HU-08 traceability). They are also enforced server-side before persistence; storing them records consent at submit time.
- `tenant_id` denormalized on the adjunct so RLS `SET LOCAL app.current_tenant_id` policies apply uniformly (same pattern as every other tenant-scoped table).

### 1.4 Document persistence (RN-015) — ARCHITECTURAL DECISION + RISK-2

The existing document upload (`booking/confirm/page.tsx` → `/reservation-events/with-documents`) persists files via `reservation_documents`, which is keyed by `group_event_id`/`reservation_id` — **there is no reservation in the wizard flow, only a Quote.** This is the same class of mismatch as `NotificationLog` (FKs reservations, not quotes). Therefore the reservation-document infrastructure is **not directly reusable for persistence**.

**Decision (MVP):** RN-015 is scoped to preserving the *client-side upload UX + MIME/size validation rules*, not to wiring the wizard into `reservation_documents`. For the MVP:
- **Frontend:** reuse the inline upload block (accept `.pdf,.jpg,.jpeg,.png`, same size messaging) — see §6.5.
- **Backend persistence option A (RECOMMENDED for MVP):** documents are OPTIONAL at wizard stage; the submit accepts them but the first slice MAY defer server-side file persistence, storing only that the requester attached N docs (count) if product needs it. This keeps the atomic write purely relational.
- **Backend persistence option B (if docs must be stored now):** add a minimal `quote_wizard_documents` table (`quote_id` FK, `storage_key`, `mime_type`, `size_bytes`, `original_filename`), reuse the same MIME/size constants (`MAX_KYC_FILE_BYTES`) and filesystem-storage pattern, writing files to a new `WIZARD_DOCUMENTS_STORAGE_PATH` after the DB commit (best-effort, like the email) OR inside the tx with rollback-safe temp files.

**RISK-2 (flag for product/tasks):** REQ-012 §data-model does not define a documents table; proposal lists only `quote_wizard_details`. `sdd-tasks`/product MUST confirm whether Step-3 documents are (a) mandatory-and-persisted now (→ option B) or (b) deferred (→ option A). Design recommends **A for the first slice** to keep the atomic path relational, with B as a clean follow-up. This design does not block on it.

### 1.5 Alembic migration outline

One additive migration `xxxx_add_portal_folio_and_wizard_details.py`:
1. `op.add_column("quotes", sa.Column("portal_folio", sa.String(32), nullable=True))`.
2. `op.execute("CREATE UNIQUE INDEX uq_quotes_portal_folio ON quotes (portal_folio) WHERE portal_folio IS NOT NULL")`.
3. `op.create_table("quote_wizard_details", ...)` with all columns above; PG `ENUM` types are auto-created by SQLAlchemy `Enum` (ensure `create_type=True` / let the first `create_table` own them). Add `sa.UniqueConstraint("quote_id")`.
4. RLS: add the standard tenant policy for `quote_wizard_details` (mirror the policy applied to `quotes`/`quote_items` — see `docs/architecture/rls-multi-tenant.md`). If policies are applied by a shared helper migration, replicate that here so the public write under `app.role=NULL` is constrained to its tenant.
5. `downgrade`: drop table, drop index, drop column, drop enum types.

> Enum evolution note: if a `values_callable` string differs from the member name, ensure the migration's `sa.Enum(..., name="tipo_evento")` uses matching values. Name each PG enum explicitly (`name="tipo_evento"`, etc.) to keep migrations deterministic.

---

## 2. Backend services & endpoints

### 2.1 DECISION: new `create_public_quote_request` service (do NOT extend `create_quote`)

**Recommendation: a new dedicated service `crm/public_service.py::create_public_quote_request(...)`.** Rationale:

1. **The pricing bug is in `create_quote`.** `create_quote` calls `get_quote_for_space(db, tenant_id, space_id, start_time, end_time)` passing two `datetime`s, but the real signature is `get_quote_for_space(db, tenant_id, space_id, target_date: date, duration_hours: Decimal)`. The wrong-typed call is swallowed by `except (ValueError, Exception)` and silently falls back to caller `precio`. Extending `create_quote` would either (a) require refactoring the internal COMMERCIAL flow's pricing semantics (out of scope, risky), or (b) branch it into two behaviors — a smell. A new service computes pricing **correctly** without touching the internal path.
2. **Different inputs.** `create_quote` requires a pre-existing `lead_id` + staff context + `QuoteItemCreate` (which carries a caller `precio`). The wizard creates the Lead in the same transaction, has no staff context, and must NOT trust a client-supplied price — it computes it server-side.
3. **Atomicity + soft-hold reuse.** The new service reuses `apply_soft_hold_for_quote(quote_id, slots, tenant_id, db)` verbatim (the multi-item atomic hold), and reuses the same "all-or-nothing within one transaction" shape — so we get atomicity without inheriting the buggy pricing loop.

The new service does NOT re-implement availability/pricing/hold — it calls the existing, correct functions. It only owns orchestration + correct types + wizard persistence.

**Signature:**

```python
# crm/public_service.py
def create_public_quote_request(
    tenant_id: UUID,
    payload: PublicQuoteRequestCreate,   # validated Pydantic DTO (see §2.3)
    db: Session,                         # already opened tenant-scoped (RLS) by the endpoint
) -> Quote:
    """
    Atomically: create Lead (requester data) + Quote(portal_folio) + QuoteItem[]
    + QuoteAdditionalService[] + QuoteWizardDetails, computing pricing with correct
    types and applying the multi-item soft-hold. Caller (endpoint) owns commit/rollback
    and RN-004 revalidation (which happens BEFORE this is called).
    Raises SlotNotAvailableError (any item unavailable) / NoPricingRuleError /
    ValueError (validation) — caller rolls back and maps to HTTP.
    """
```

**Internal pricing call (the corrected pattern):**

```python
from decimal import Decimal
from datetime import datetime

def _duration_hours(hora_inicio: time, hora_fin: time, fecha: date) -> Decimal:
    start = datetime.combine(fecha, hora_inicio)
    end = datetime.combine(fecha, hora_fin)
    secs = (end - start).total_seconds()
    return Decimal(str(secs / 3600.0)).quantize(Decimal("0.01"))

# per item:
breakdown = calculate_price(
    space_id=item.space_id,
    duration_hours=_duration_hours(item.hora_inicio, item.hora_fin, item.fecha),  # Decimal
    tenant_id=tenant_id,
    target_date=item.fecha,   # date object, NOT datetime
    db=db,
)
item_price = breakdown.total_price  # Decimal — NO broad except / NO caller-supplied fallback
```

`NoPricingRuleError` is **propagated** (not swallowed): a wizard item on a space with no pricing rule is a real error, surfaced to the user, not a silent default. (This directly satisfies spec Scenario "Pricing call uses correct types, not the broken create_quote pattern".)

**Persistence order inside the service (single tx):**
1. `Lead` from Step-3 requester data (`name=nombre_completo`, `email=correo_institucional`, `phone=telefono_contacto`, `company=institucion_organizacion`, `notes=` compact wizard summary). `db.add(lead); db.flush()`.
2. `Quote(tenant_id, lead_id=lead.id, status=QuoteStatus.DRAFT, total=aggregate, portal_folio=payload.folio)`. `flush()`.
3. `QuoteItem[]` (one per Step-2 block, `precio=item_price`, `item_order=i`). `flush()`.
4. `QuoteAdditionalService[]` for each `servicios_apoyo` (compute `calculated_price` via catalog service or store selected qty). `flush()`.
5. `QuoteWizardDetails` (all Step 1/3/4 + legal flags). `flush()`.
6. `apply_soft_hold_for_quote(quote.id, slots, tenant_id, db)` — atomic multi-item hold; raises `SlotNotAvailableError` if any slot no longer AVAILABLE → caller rolls back the whole tx.

`status` uses existing `QuoteStatus.DRAFT` default (no new state; assumption honored). Return the `Quote`.

### 2.2 Endpoints (`api/public.py`, prefix `/api`, tag `public`, no JWT)

**Gate endpoint (RN-001/002/003/017):**
```
POST /api/public/quote-requests/validate-folio
body: { "folio": "BCE-20260715-172822-2973" }
200 → { "unlocked": true, "folio": "...", "portal_status": "quotation_in_progress" }
422 → format invalid (RN-017)              # FastAPI/Pydantic validation, no Portal call
403 → { "unlocked": false, "reason": "FOLIO_NOT_ELIGIBLE", "message": <RN-003 text> }
503 → { "reason": "PORTAL_UNAVAILABLE", "message": "Portal no disponible, intenta más tarde." }
```
- REQ §9.1 Portal contract: `GET {PORTAL_API_BASE_URL}/api/public/space-event-requests/access/{folio}` → 200 (payload w/ status) / 403 / 404.
- Format regex checked first (RN-017): `^BCE-\d{8}-\d{6}-\d{4}$`. On mismatch → 422, **no** outbound call (spec: "no outbound HTTP request to Portal is made").
- Both Portal `404` (not found) and `200`-with-status≠`quotation_in_progress` and `403` map to the SAME RN-003 block (403 + fixed message). Portal timeout/5xx-exhausted maps to **503 PORTAL_UNAVAILABLE** (distinct taxonomy, spec-required).

**Submit endpoint (RN-004/005…011/012/013/014/016):**
```
POST /api/public/quote-requests
body: PublicQuoteRequestCreate (full wizard payload; see §2.3)
201 → { "quote_id": "...", "total": "...", "email_sent": true|false, "message": <≤24h hábiles> }
422 → server-side field/conditional/legal validation failure (RN-005..011, RN-014)
403 → RN-004 revalidation failed (folio no longer quotation_in_progress / not found)
409 → { "reason": "SLOT_UNAVAILABLE" | "DUPLICATE_FOLIO" }   # any item unavailable OR portal_folio replay
503 → PORTAL_UNAVAILABLE at submit-time revalidation
```
- Content type: for MVP option A (docs deferred) this is `application/json`. If docs must be persisted at submit (option B), it becomes `multipart/form-data` with a `payload` JSON part + `files` (mirroring `booking/confirm`). Design keeps JSON for the first slice.

### 2.3 Request DTOs (`crm/schemas.py`) — server-side validation is the source of truth

`PublicQuoteRequestCreate` composes step models; Pydantic validators enforce RN rules server-side (independent of client):

```python
class PublicWizardItem(BaseModel):
    space_id: UUID
    fecha: date
    hora_inicio: time
    hora_fin: time
    # NO client `precio` — server computes it.

class PublicQuoteRequestCreate(BaseModel):
    folio: str = Field(..., pattern=r"^BCE-\d{8}-\d{6}-\d{4}$")   # RN-017 also here
    # Step 1
    tipo_evento: TipoEvento
    nombre_evento: str | None = None
    caracter_evento: CaracterEvento
    descripcion_evento: str | None = None
    asistentes_estimados: int = Field(..., gt=0)                  # RN-007
    habra_prensa: bool
    # Step 2
    items: list[PublicWizardItem] = Field(..., min_length=1)      # RN-012 multi-item
    # Step 3
    nombre_completo: str = Field(..., min_length=1)
    cargo_puesto: str | None = None
    institucion_organizacion: str | None = None
    sector: Sector
    sector_otro: str | None = None
    correo_institucional: EmailStr
    telefono_contacto: str = Field(..., min_length=1)
    responsable_sitio_nombre: str | None = None
    responsable_sitio_telefono: str | None = None
    como_conociste_bloque: ComoConociste
    como_conociste_otro: str | None = None
    # Step 4
    servicios_apoyo: list[WizardServiceSelection] = []           # {service_id, quantity}
    montaje_requerido: MontajeRequerido
    requerimientos_especiales: str | None = None
    material_externo: bool = False
    material_externo_detalle: str | None = None
    # Step 5 (RN-014)
    acepta_info_correcta_autorizacion: bool
    acepta_reglamento_y_aviso_privacidad: bool

    @model_validator(mode="after")
    def _conditionals(self):
        if self.tipo_evento == TipoEvento.OTRO and not (self.nombre_evento or "").strip():
            raise ValueError("nombre_evento requerido cuando tipo_evento=Otro")     # RN-008
        if self.sector == Sector.OTRO and not (self.sector_otro or "").strip():
            raise ValueError("sector_otro requerido cuando sector=Otro")            # RN-009
        if self.como_conociste_bloque == ComoConociste.OTRO and not (self.como_conociste_otro or "").strip():
            raise ValueError("como_conociste_otro requerido cuando Otro")           # RN-010
        if self.material_externo and not (self.material_externo_detalle or "").strip():
            raise ValueError("material_externo_detalle requerido")                  # RN-011
        if self.descripcion_evento and len(self.descripcion_evento.split()) > 300:
            raise ValueError("descripcion_evento excede 300 palabras")              # RN-006
        if not (self.acepta_info_correcta_autorizacion and self.acepta_reglamento_y_aviso_privacidad):
            raise ValueError("Ambas aceptaciones legales son requeridas")           # RN-014
        return self
```

Pydantic `ValidationError` → FastAPI 422 automatically, satisfying every "rejected server-side, nothing persisted" scenario (validation runs before any DB write).

---

## 3. Portal gate client (`modules/portal_gate/`)

New isolated adapter — the only outbound HTTP in the codebase, so it establishes the pattern.

```python
# modules/portal_gate/client.py
class PortalFolioStatus(str, enum.Enum):
    ELIGIBLE = "eligible"            # 200 & status == quotation_in_progress
    NOT_ELIGIBLE = "not_eligible"    # 404, 403, or 200 with other status  → RN-003
    UNAVAILABLE = "unavailable"      # timeout/5xx after retries            → 503

class PortalGateError(Exception): ...
class PortalUnavailableError(PortalGateError): ...   # distinct taxonomy branch

def validate_folio(folio: str) -> PortalFolioStatus:
    """
    GET {settings.PORTAL_API_BASE_URL}/api/public/space-event-requests/access/{folio}
    Retries transient failures (timeout, 5xx) up to N (config, default 3) with
    exponential-ish backoff. Maps:
      200 + body.status == 'quotation_in_progress' -> ELIGIBLE
      200 + other status                            -> NOT_ELIGIBLE
      404 / 403                                     -> NOT_ELIGIBLE
      timeout / ConnectError / 5xx (exhausted)      -> raise PortalUnavailableError
    """
```

**Implementation details:**
- `httpx.Client(timeout=httpx.Timeout(5.0, connect=3.0))` — fail fast; gate/submit are must-block-and-wait.
- Retry policy: `attempts = settings.PORTAL_RETRY_ATTEMPTS` (default 3, i.e. 1 initial + 2 retries → "2-3 attempts"). Backoff: `sleep(0.2 * 2**i)` between attempts (≈0.2s, 0.4s). Retry ONLY on `httpx.TimeoutException`, `httpx.ConnectError`, and `resp.status_code >= 500`. Do NOT retry `403/404` (those are deterministic → `NOT_ELIGIBLE`).
- Error taxonomy (three-way, spec-required):
  - **FormatInvalid** — handled BEFORE the client, at the DTO/regex layer (422). The client is never called for a malformed folio.
  - **NotFound / WrongStatus / AccessDenied** → `NOT_ELIGIBLE` → gate 403 with the fixed RN-003 message.
  - **PortalUnavailable** → `PortalUnavailableError` → gate/submit 503 `PORTAL_UNAVAILABLE`, distinct from RN-003.
- **RN-002 (gate) and RN-004 (submit revalidation) both call the SAME `validate_folio`.** Gate: on `ELIGIBLE` → 200 unlocked; else block. Submit: revalidate FIRST (before opening the write tx) — on `ELIGIBLE` proceed; `NOT_ELIGIBLE` → 403 no-persist; `UNAVAILABLE` → 503 no-persist.
- **Auth header hook:** if Portal later requires API key/HMAC (stated assumption), add `headers={"X-Api-Key": settings.PORTAL_API_KEY}` config-driven — no flow change.
- Synchronous `httpx.Client` (not async) because the public endpoints are sync `def` using `get_db_context` (matching `list_sedes`). Keeps the transaction model simple.

---

## 4. Atomicity & RLS

### 4.1 Tenant-scoped public session

Endpoints resolve tenant from config (NOT session), reusing the catalog fallback semantics:

```python
tenant_id = settings.DEFAULT_TENANT_ID  # or optional_tenant_for_catalog fallback to first active tenant
with get_db_context(tenant_id=str(tenant_id), role=None) as db:
    ...
```

`get_db_context(tenant_id=..., role=None)` sets `SET LOCAL app.current_tenant_id` via the `after_begin` listener (re-applied at the start of every transaction, including post-commit), so RLS policies constrain all reads/writes to the sede. `role=None` (not `"SUPERADMIN"`) so the public write is a normal tenant-scoped actor, not a policy-bypassing superadmin. (Contrast `list_sedes`, which uses `role="SUPERADMIN"` to list all tenants — the write path must NOT.)

> RLS prerequisite: the migration MUST attach the tenant RLS policy to `quote_wizard_details` (and `quote_wizard_documents` if option B), else inserts under `app.role=NULL` fail or leak. Covered in §1.5 step 4.

### 4.2 Transaction boundary (endpoint owns commit)

```
# submit endpoint
1. Validate DTO (Pydantic)  -> 422 on failure (no DB touched)         # RN-005..011, RN-014, RN-017
2. status = portal_gate.validate_folio(payload.folio)                 # RN-004 — BEFORE any write tx
   - NOT_ELIGIBLE -> 403, return (nothing opened)
   - UNAVAILABLE  -> 503, return (nothing opened)
   - ELIGIBLE     -> continue
3. with get_db_context(tenant_id=..., role=None) as db:
       try:
           # 3a. Multi-item availability gate (RN-012): fail whole submit if any unavailable
           group = check_group_availability(
               [{"espacio_id": it.space_id, "fecha": it.fecha,
                 "hora_inicio": it.hora_inicio, "hora_fin": it.hora_fin} for it in payload.items],
               db=db, role=None,
           )
           if not group["all_available"]:
               raise SlotNotAvailableError(group["conflicts"])        # -> 409 SLOT_UNAVAILABLE
           # 3b. Atomic persist + correct pricing + soft-hold
           quote = create_public_quote_request(tenant_id, payload, db)
           db.commit()                                                # single atomic commit
       except (SlotNotAvailableError, IntegrityError, NoPricingRuleError, ValueError):
           db.rollback()                                              # nothing persists
           -> map to 409 / 422
4. best-effort email AFTER commit (see §5)
5. 201 with quote_id + total + email_sent + ≤24h message
```

- **RN-004 sits BEFORE the write tx** (step 2). If the folio is no longer eligible or Portal is down, no transaction is opened and nothing is persisted — exactly the spec's "nothing persists" / "no records are persisted" scenarios.
- **Multi-item atomicity:** `check_group_availability` is a pre-check (fast fail with a clear conflict list). The authoritative guard is `apply_soft_hold_for_quote` inside the tx, which does `SELECT ... FOR UPDATE` per slot and raises `SlotNotAvailableError` if any slot changed between pre-check and hold (TOCTOU-safe). Either raise → full `rollback()` → zero rows (Lead, Quote, items, services, wizard_details, holds all gone). Satisfies "One item unavailable — entire submit fails, nothing persisted."
- **Replay/duplicate folio:** the partial unique index raises `IntegrityError` on `commit()` → caught → `rollback()` → 409 `DUPLICATE_FOLIO`. Satisfies "portal_folio uniqueness is enforced."
- **No user account:** the service creates only `Lead` + quote graph; no `User` row anywhere. Satisfies "No user account is created."

### 4.3 Why check_group_availability + soft-hold (both)

`check_group_availability` gives a friendly, per-item conflict report for the 409 body (good UX). `apply_soft_hold_for_quote` is the transactional truth (locks rows). Using both = good errors + correct concurrency. This mirrors how the internal flow relies on the FOR UPDATE hold as the real gate.

### 4.4 Error → HTTP mapping (single table)

| Condition | Where | HTTP | Body |
| :-- | :-- | :-- | :-- |
| Folio format invalid (RN-017) | DTO regex | 422 | validation error; no Portal call |
| Field/conditional/legal invalid (RN-005..011,014) | Pydantic | 422 | field error; no DB write |
| Portal says not-eligible (gate) | gate | 403 | RN-003 message |
| Portal unavailable (gate) | gate | 503 | PORTAL_UNAVAILABLE |
| RN-004 revalidation not-eligible | submit | 403 | not-eligible; nothing persisted |
| RN-004 revalidation unavailable | submit | 503 | PORTAL_UNAVAILABLE; nothing persisted |
| Any item unavailable | submit tx | 409 | SLOT_UNAVAILABLE + conflicts |
| Duplicate portal_folio | submit commit | 409 | DUPLICATE_FOLIO |
| No pricing rule for a space | submit tx | 409/422 | NO_PRICING_RULE (decide in tasks) |
| Success | submit | 201 | quote_id, total, email_sent, ≤24h message |

---

## 5. Best-effort, non-blocking confirmation email (RN-016)

Placement: **after `db.commit()`**, in the endpoint (not inside the service, so a mail failure can never touch the tx).

```python
email_sent = False
try:
    html = render("public_quote_confirmation.html", quote=quote, lead=lead, folio=payload.folio, ...)
    send_email(to=payload.correo_institucional, subject="Recibimos tu solicitud de cotización", html_body=html)
    email_sent = True
except Exception as exc:
    logger.warning("Confirmation email failed for quote %s: %s", quote.id, exc)
# always return 201 + confirmation payload regardless of email_sent
```

- Reuse `notifications/templating.py::render(template_name, **ctx)` + `notifications/email_service.py::send_email(to, subject, html_body, ...)`. New Jinja template `notifications/templates/public_quote_confirmation.html` with the recepción/revisión ≤24h hábiles copy.
- **No `NotificationLog`** (it FKs reservations, not quotes) — spec-required. Single one-shot email.
- Synchronous try/except (not Celery) is simplest and satisfies "best-effort non-blocking" — the exception is caught, submit still 201, failure logged, confirmation screen shown. (Celery is an option but adds a dependency on broker availability for a fire-and-forget mail; sync+try/except is lower risk for MVP. Flag as a minor choice for tasks.)

---

## 6. Frontend (public wizard)

### 6.1 Route group (basePath-safe)

New route group `src/frontend/app/(public-wizard)/` (parentheses = no URL segment). Pages:
- `/solicitud` — folio gate screen (input + validate).
- `/solicitud/wizard` — the 5-step wizard (single client page driving steps from the Zustand store, OR nested step routes; single page recommended to keep state trivially in memory).
- `/solicitud/confirmacion` — success screen (≤24h hábiles).

All are `"use client"` (stateful, event handlers, controlled inputs). Mutations via existing Axios `apiClient` (`lib/http/apiClient.ts`, `baseURL: NEXT_PUBLIC_API_URL || '/api'`). basePath is handled by Next config + `redirectUrl()` helper already in middleware; use relative `router.push('/solicitud/...')` (App Router applies basePath).

### 6.2 Middleware whitelist (CRITICAL)

`middleware/auth-middleware.ts` — extend `isPublicPage` (currently only `/` and `/catalog`):
```ts
const isPublicPage =
  request.nextUrl.pathname === '/' ||
  request.nextUrl.pathname.startsWith('/catalog') ||
  request.nextUrl.pathname.startsWith('/solicitud');   // NEW: public wizard
```
Without this, anonymous access to `/solicitud*` redirects to `/login` (the known middleware gap). `request.nextUrl.pathname` is already basePath-stripped, so `startsWith('/solicitud')` is correct.

### 6.3 Zustand store shape (multi-step + multi-item)

New `features/quote-wizard/store/quote-wizard.store.ts` (mirrors `event-cart.store.ts` conventions, no RHF/Zod):

```ts
interface WizardItem {          // Step 2, multi-space/multi-day
  spaceId: string;
  fecha: string;                // YYYY-MM-DD
  horaInicio: string;           // HH:mm
  horaFin: string;
  cotizacionCalculada?: number; // from availability+pricing preview call
}
interface ServiceSelection { serviceId: string; quantity: number; }

interface QuoteWizardState {
  // gate
  folio: string;
  folioUnlocked: boolean;
  // step 1
  tipoEvento: string; nombreEvento: string; caracterEvento: string;
  descripcionEvento: string; asistentesEstimados: number; habraPrensa: boolean;
  // step 2
  items: WizardItem[];
  // step 3
  nombreCompleto: string; cargoPuesto: string; institucionOrganizacion: string;
  sector: string; sectorOtro: string; correoInstitucional: string; telefonoContacto: string;
  responsableSitioNombre: string; responsableSitioTelefono: string;
  comoConociste: string; comoConocisteOtro: string;
  documents: Record<string, File | File[]>;   // reused upload block state
  // step 4
  serviciosApoyo: ServiceSelection[];
  montajeRequerido: string; requerimientosEspeciales: string;
  materialExterno: boolean; materialExternoDetalle: string;
  // step 5
  aceptaInfoCorrecta: boolean; aceptaReglamento: boolean;
  // nav
  currentStep: 1 | 2 | 3 | 4 | 5;
  // actions
  setField<K extends keyof QuoteWizardState>(k: K, v: QuoteWizardState[K]): void;
  addItem(i: WizardItem): void; removeItem(idx: number): void;
  goNext(): void; goBack(): void; reset(): void;
}
```

- Store holds ALL state until the single atomic submit (matches backend's all-or-nothing; no partial persistence). No `persist` middleware needed for MVP (refresh loses progress — acceptable; flag if product wants sessionStorage persistence).
- React 19 / compiler: no `useMemo`/`useCallback`; named imports from `react`; `ref` as prop.

### 6.4 Client-side step guards (mirror server)

Per-step `canAdvance` computed in the component (plain derived values, no memo):
- Step 1: `tipoEvento` set; if `Otro` → `nombreEvento` non-empty (RN-008); `asistentesEstimados > 0` (RN-007); `descripcionEvento` ≤300 words (RN-006); `caracterEvento`, `habraPrensa` set.
- Step 2: ≥1 item; each item availability-confirmed + priced via a preview call (see §6.6).
- Step 3: required fields; `sector==Otro→sectorOtro` (RN-009); `comoConociste==Otro→comoConocisteOtro` (RN-010); email/phone present.
- Step 4: `montajeRequerido` set; `materialExterno→materialExternoDetalle` (RN-011).
- Step 5: submit disabled until BOTH acceptances true (RN-014).

These are UX only; the server re-validates everything (client can be bypassed → server 422). This satisfies "even if the client-side check was bypassed" scenarios.

### 6.5 Document-upload block (RN-015)

Adapt the inline block from `booking/confirm/page.tsx` (lines ~901–1082): drag-drop `<label>` + hidden `<input type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png">`, `pendingFiles` state → `store.documents`. Keep identical MIME/size messaging (no rule change). Extract into `features/quote-wizard/components/DocumentUpload.tsx` for reuse. Per §1.4, for MVP option A these files may be collected client-side and not POSTed (or POSTed as multipart if option B). No functional change to the validation rules themselves — satisfies RN-015.

### 6.6 Availability + pricing preview (Step 2)

Step 2 calls existing PUBLIC-safe endpoints to fill `cotizacionCalculada` before submit:
- Availability: existing `POST /spaces/check-availability` / group variant (already `optional_tenant_for_catalog`, public-safe).
- Pricing preview: reuse the catalog/pricing read the `booking/confirm` page uses (`/spaces`, `/pricing-rules`) OR a small public pricing-preview endpoint if needed. The **authoritative** price is always recomputed server-side at submit (client preview is advisory).

---

## 7. Config (`core/config.py`)

Add to `Settings`:
```python
# BLOQUE Portal gate (folio validation) — REQ-012
PORTAL_API_BASE_URL: str = "https://portal.bloque.example"   # distinct from existing PORTAL_BASE_URL (display/link)
PORTAL_RETRY_ATTEMPTS: int = 3                                # 1 initial + 2 retries
PORTAL_API_KEY: str | None = None                            # optional; header added only if set (assumption)
# Legal copy URLs (placeholders until legal supplies canonical docs) — RN-014 links
LEGAL_REGLAMENTO_URL: str = "https://bloque.example/reglamento"
LEGAL_AVISO_PRIVACIDAD_URL: str = "https://bloque.example/aviso-privacidad"
# Only if document option B is chosen:
# WIZARD_DOCUMENTS_STORAGE_PATH: str = "data/wizard_documents"
```
- `DEFAULT_TENANT_ID` already exists → reuse for sede resolution (do NOT invent a new sede setting).
- `PORTAL_API_BASE_URL` is NEW and distinct from the existing `PORTAL_BASE_URL` (which is a display/link URL). Frontend legal-link envs (`NEXT_PUBLIC_LEGAL_*`) may mirror these for the checkboxes.

---

## 8. Testing approach (pytest, real DB, mocked Portal)

Integration-first, mirroring the module's existing style (`get_db_context`, real Postgres, `TestClient`). Mock ONLY the Portal httpx boundary (`portal_gate.client.validate_folio` or the `httpx` transport) — everything else exercises real DB + real inventory/pricing.

**Gate tests (`test_public_quote_gate.py`):**
- Well-formed folio + Portal `quotation_in_progress` → 200 unlocked (RN-001/002).
- Malformed folio → 422 AND assert the Portal client/httpx was NEVER called (spy/`assert_not_called`) (RN-017).
- Portal 404 / 403 / status≠quotation_in_progress → 403 with RN-003 message (RN-003).
- Portal timeout×N (retries exhausted) → 503 PORTAL_UNAVAILABLE, distinct from 403 (resilience req).
- Portal timeout then success → 200 (assert retry happened) (resilience req).

**Submit tests (`test_public_quote_submit.py`):**
- Happy path multi-item (3 items, distinct spaces/dates) → 201; assert Quote.total == sum of engine prices, 3 QuoteItems, QuoteWizardDetails row, portal_folio set, Lead created, NO User row (RN-012/013).
- **Multi-item atomic rollback:** 3 items, pre-block 1 slot (SOFT_HOLD via `apply_soft_hold_for_quote` for another quote) → 409; assert DB has ZERO Lead/Quote/QuoteItem/QuoteAdditionalService/QuoteWizardDetails for this attempt (RN-012 atomicity).
- **Correct pricing (regression on the create_quote bug):** seed a PricingRule; submit; assert computed price equals `calculate_price(...)` result, NOT any client-sent default. Also assert a `space` with NO pricing rule → error (not silent fallback) (RN-012 correct-types scenario).
- RN-004: gate-time eligible, but mock Portal to return not-eligible at submit → 403, zero rows.
- RN-004 unavailable at submit → 503, zero rows.
- Conditional validation matrix (parametrized): tipo_evento=Otro w/o nombre (RN-008), sector=Otro w/o sector_otro (RN-009), como_conociste=Otro w/o detalle (RN-010), material_externo=true w/o detalle (RN-011), descripcion>300 words (RN-006), asistentes≤0 (RN-007), each legal acceptance false/missing (RN-014) → 422, zero rows.
- Duplicate folio replay → 409 DUPLICATE_FOLIO, no second Quote (RN-013 uniqueness).
- No-auth access: gate + submit succeed with no Authorization header (public req).
- Tenant resolution: assert persisted rows carry `tenant_id == DEFAULT_TENANT_ID`.

**Email tests (RN-016):**
- Mock `send_email` to raise → assert submit still 201, `email_sent=false`, failure logged, NO NotificationLog row written.
- Mock `send_email` success → 201, `email_sent=true`.

**Frontend:** (if in scope for this change's tests) e2e/Playwright — anonymous `/solicitud` NOT redirected to `/login` (middleware whitelist), and submit-disabled-until-both-acceptances. Otherwise covered manually; backend integration tests carry the invariants.

Markers: `@pytest.mark.integration`. Fixtures: reuse the project's DB session/tenant fixtures; add a `mock_portal` fixture that patches `portal_gate.client` with configurable responses (eligible / not-eligible / timeout-then-ok / always-timeout).

---

## 9. Risks & ambiguities (explicit)

- **RISK-1 (enum values):** exact catalog values for `TipoEvento/CaracterEvento/Sector/ComoConociste/MontajeRequerido` are not frozen by REQ-012 text. Defaults provided; `sdd-tasks`/product MUST confirm before migration (enum values are costly to change post-migration). Non-blocking for architecture.
- **RISK-2 (document persistence):** reservation-document infra is reservation-scoped, not quote-scoped (same mismatch class as NotificationLog). Design recommends MVP option A (collect client-side, defer server persistence) with a clean option B (`quote_wizard_documents` table). Product/tasks MUST pick. RN-015 (preserve MIME/size UX rules) is satisfiable either way.
- **RISK-3 (pricing rule gaps):** wizard spaces without a `PricingRule` for the date raise `NoPricingRuleError`. Decide the HTTP mapping (409 vs 422) and UX copy in tasks. Do NOT silently default (that was the bug).
- **RISK-4 (Portal contract details):** exact `200` body shape for status field (`status` key name/values) per REQ §9.1 must be confirmed against the real Portal; the client's status-extraction is the only place that depends on it. Auth (API key/HMAC) assumed absent for MVP; hook provided.
- **RISK-5 (sync vs Celery email):** design uses sync try/except for simplicity; if the team prefers Celery fire-and-forget, it's a drop-in at §5 without changing the atomicity guarantees.
- **RISK-6 (state persistence):** Zustand store is in-memory; a page refresh loses wizard progress. Acceptable for MVP; add `persist` (sessionStorage) if product requires resume.

## 10. ADR summary

- **ADR-1:** New `create_public_quote_request` service instead of extending `create_quote`. Rationale: isolates the corrected pricing call, avoids branching the internal COMMERCIAL flow, no client-trusted price, reuses `apply_soft_hold_for_quote` for atomic multi-item hold. Rejected: extending `create_quote` (would entangle the bug fix with internal semantics and require staff-context assumptions).
- **ADR-2:** `portal_folio` on `Quote` with a partial unique index (`WHERE portal_folio IS NOT NULL`). Rejected: on `Lead` (write path is quote-centric; RN-004 is a quote-submit check), or a separate mapping table (folio↔quote is 1:1 in MVP).
- **ADR-3:** Wizard-only fields in a 1:1 `quote_wizard_details` adjunct. Rejected: widening `quotes`/`leads` (pollutes the internal flow), or JSON blob (loses queryability/typed enums).
- **ADR-4:** RN-004 revalidation BEFORE opening the write transaction. Rejected: revalidate inside the tx (would open+rollback a tx unnecessarily and risk partial side-effects); revalidate only at gate (violates RN-004).
- **ADR-5:** Isolated `portal_gate` httpx adapter with a 3-way status enum + distinct `PortalUnavailableError`. Rejected: inline httpx in the endpoint (untestable, no clean taxonomy).
- **ADR-6:** Best-effort email via sync try/except after commit, no NotificationLog. Rejected: emailing inside the tx (a mail failure could roll back a valid quote); NotificationLog (FKs reservations, not quotes).
- **ADR-7:** Public route group `(public-wizard)` + `/solicitud*` added to `isPublicPage`; single Zustand store, controlled inputs, no RHF/Zod. Rejected: introducing a form library (no precedent, out of scope).
