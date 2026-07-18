# Spec Delta: Solicitud de Cotización mediante Folio de BLOQUE Portal (`quote-request-folio`)

**Source:** REQ-012, proposal `openspec/changes/quote-request-folio/proposal.md`
**Module:** `crm` (extends `Lead → Quote → QuoteItem`), `inventory`, `pricing`, `notifications`, `api/public`, frontend public wizard.

This is a delta spec: it describes what MUST be true of the system after this change is applied. Each Requirement has at least one Scenario in GIVEN/WHEN/THEN form; negative/edge scenarios are included per requirement where applicable.

---

## Requirement: Folio format validation (RN-017)

The system MUST validate the folio format `BCE-YYYYMMDD-HHMMSS-RRRR` on the backend before calling the BLOQUE Portal API.

### Scenario: Well-formed folio passes format check
- GIVEN a solicitante submits folio `BCE-20260715-172822-2973` to the gate endpoint
- WHEN the backend validates its format
- THEN the format check passes and the backend proceeds to call the BLOQUE Portal API

### Scenario: Malformed folio is rejected before any Portal call
- GIVEN a solicitante submits a folio that does not match `BCE-YYYYMMDD-HHMMSS-RRRR` (e.g. `ABC-123`, empty string, or a folio missing segments)
- WHEN the gate endpoint validates the format
- THEN the backend returns a validation error WITHOUT calling the Portal API
- AND no outbound HTTP request to Portal is made (verifiable via mock/spy in tests)

---

## Requirement: Folio gate — Portal status validation (RN-001, RN-002, RN-003)

The system MUST call the BLOQUE Portal API to confirm the folio's status is `quotation_in_progress` before unlocking the wizard, and MUST block with a distinct reason otherwise.

### Scenario: Valid folio in quotation_in_progress unlocks the wizard
- GIVEN a folio with valid format that Portal reports as status `quotation_in_progress`
- WHEN the solicitante submits the folio to the public gate endpoint
- THEN the endpoint returns `200` with a payload indicating the wizard is unlocked
- AND no authentication (JWT) is required for this call

### Scenario: Folio not found is blocked with RN-003 message
- GIVEN a folio with valid format that Portal reports as not found (`404`)
- WHEN the solicitante submits the folio to the gate endpoint
- THEN the endpoint returns a blocked response with the RN-003 message: "El folio proporcionado no se encuentra disponible para iniciar una cotización. Verifica el estatus en BLOQUE Portal."
- AND the wizard does NOT unlock

### Scenario: Folio with wrong/terminal status is blocked with RN-003 message
- GIVEN a folio with valid format that Portal reports as a status other than `quotation_in_progress` (e.g. `quotation_sent`, `closed`, `rejected`)
- WHEN the solicitante submits the folio to the gate endpoint
- THEN the endpoint returns a blocked response with the RN-003 message
- AND the wizard does NOT unlock

### Scenario: Access denied by Portal is blocked with RN-003 message
- GIVEN a folio with valid format that Portal reports as access denied (`403`)
- WHEN the solicitante submits the folio to the gate endpoint
- THEN the endpoint returns a blocked response with the RN-003 message
- AND the wizard does NOT unlock

---

## Requirement: Portal client resilience — timeout/5xx retry and distinct error taxonomy

The Portal gate HTTP client MUST retry transient failures 2-3 times with backoff and surface a distinct "Portal unavailable" error, separate from "folio invalid/wrong status", when retries are exhausted.

### Scenario: Transient timeout is retried then succeeds
- GIVEN the Portal API times out on the first call for a given folio but succeeds on a subsequent retry
- WHEN the gate endpoint calls the Portal client
- THEN the client retries (up to the configured 2-3 attempts) with backoff
- AND if a retry succeeds, the gate proceeds using that successful response

### Scenario: Portal unavailable after exhausting retries returns a distinct error
- GIVEN the Portal API times out or returns 5xx on every attempt (2-3 retries exhausted)
- WHEN the gate endpoint calls the Portal client
- THEN the endpoint returns an error distinct from the RN-003 "folio invalid/wrong status" message — e.g. a "Portal unavailable, try again later" error
- AND this error is distinguishable in the response (different error code/type) from the RN-003 block response
- AND the wizard does NOT unlock

---

## Requirement: Revalidation on submit (RN-004)

The system MUST revalidate the folio against Portal at submit time (Step 5) and reject the submission — persisting nothing — if the folio is no longer `quotation_in_progress`.

### Scenario: Folio still valid at submit — request persists
- GIVEN a solicitante completed all 5 wizard steps with a folio that was `quotation_in_progress` at gate time
- AND the folio is still `quotation_in_progress` when Hub revalidates at submit
- WHEN the solicitante submits the wizard
- THEN Hub persists the Lead, Quote, QuoteItem(s), QuoteAdditionalService(s), and quote_wizard_details row
- AND the response confirms success

### Scenario: Folio status changed before submit — nothing persists
- GIVEN a solicitante completed all 5 wizard steps with a folio that was `quotation_in_progress` at gate time
- AND by the time of submit, Portal now reports the folio's status as something else (e.g. `quotation_sent`) or not found
- WHEN the solicitante submits the wizard
- THEN the submit is rejected with a controlled error
- AND NO Lead, Quote, QuoteItem, QuoteAdditionalService, or quote_wizard_details row is created (verify via DB query / rollback)

### Scenario: Portal unavailable at submit-time revalidation
- GIVEN a solicitante completed all 5 wizard steps
- AND Portal is unavailable (timeout/5xx exhausted retries) when Hub attempts revalidation at submit
- WHEN the solicitante submits the wizard
- THEN the submit is rejected with the distinct "Portal unavailable" error
- AND NO records are persisted

---

## Requirement: Step 1 server-side validation — required fields and descripcion_evento word limit (RN-005, RN-006)

The system MUST enforce Step 1 required fields and the 300-word limit on `descripcion_evento` on the backend, independent of client-side validation.

### Scenario: Missing required Step 1 field is rejected server-side
- GIVEN a submit payload missing a required Step 1 field (e.g. `tipo_evento`, `caracter_evento`, or `habra_prensa`)
- WHEN the backend validates the submission
- THEN the backend rejects the request with a validation error identifying the missing field
- AND nothing is persisted

### Scenario: descripcion_evento within 300 words is accepted
- GIVEN a submit payload where `descripcion_evento` contains 300 words or fewer
- WHEN the backend validates Step 1
- THEN the word-count validation passes

### Scenario: descripcion_evento exceeding 300 words is rejected server-side
- GIVEN a submit payload where `descripcion_evento` contains more than 300 words
- WHEN the backend validates Step 1 (even if the client-side check was bypassed)
- THEN the backend rejects the request with a validation error
- AND nothing is persisted

---

## Requirement: Step 1 server-side validation — asistentes_estimados positive integer (RN-007)

The system MUST validate `asistentes_estimados` is a positive integer on the backend.

### Scenario: Positive integer accepted
- GIVEN a submit payload with `asistentes_estimados = 50`
- WHEN the backend validates Step 1
- THEN the validation passes

### Scenario: Zero or negative asistentes_estimados rejected
- GIVEN a submit payload with `asistentes_estimados = 0` or `asistentes_estimados = -5`
- WHEN the backend validates Step 1
- THEN the backend rejects the request with a validation error
- AND nothing is persisted

---

## Requirement: Conditional field validation — tipo_evento Otro (RN-008)

The system MUST require `nombre_evento` server-side when `tipo_evento = Otro`.

### Scenario: tipo_evento Otro without nombre_evento is rejected
- GIVEN a submit payload with `tipo_evento = "Otro"` and `nombre_evento` empty/missing
- WHEN the backend validates Step 1
- THEN the backend rejects the request with a validation error requiring `nombre_evento`
- AND nothing is persisted

### Scenario: tipo_evento Otro with nombre_evento provided is accepted
- GIVEN a submit payload with `tipo_evento = "Otro"` and `nombre_evento = "Foro Regional de Innovación"`
- WHEN the backend validates Step 1
- THEN the validation passes

### Scenario: tipo_evento not Otro does not require nombre_evento
- GIVEN a submit payload with `tipo_evento = "Conferencia"` and `nombre_evento` empty/missing
- WHEN the backend validates Step 1
- THEN the validation passes (nombre_evento is not required)

---

## Requirement: Conditional field validation — sector Otro (RN-009)

The system MUST require `sector_otro` server-side when `sector = Otro`.

### Scenario: sector Otro without sector_otro is rejected
- GIVEN a submit payload with `sector = "Otro"` and `sector_otro` empty/missing
- WHEN the backend validates Step 3
- THEN the backend rejects the request with a validation error
- AND nothing is persisted

### Scenario: sector Otro with sector_otro provided is accepted
- GIVEN a submit payload with `sector = "Otro"` and `sector_otro = "Fideicomiso público"`
- WHEN the backend validates Step 3
- THEN the validation passes

---

## Requirement: Conditional field validation — como_conociste_bloque Otro (RN-010)

The system MUST require `como_conociste_otro` server-side when `como_conociste_bloque = Otro`.

### Scenario: como_conociste_bloque Otro without como_conociste_otro is rejected
- GIVEN a submit payload with `como_conociste_bloque = "Otro"` and `como_conociste_otro` empty/missing
- WHEN the backend validates Step 3
- THEN the backend rejects the request with a validation error
- AND nothing is persisted

### Scenario: como_conociste_bloque Otro with detail provided is accepted
- GIVEN a submit payload with `como_conociste_bloque = "Otro"` and `como_conociste_otro = "Evento de cámara empresarial"`
- WHEN the backend validates Step 3
- THEN the validation passes

---

## Requirement: Conditional field validation — material_externo detalle (RN-011)

The system MUST require `material_externo_detalle` server-side when `material_externo = true`.

### Scenario: material_externo true without detalle is rejected
- GIVEN a submit payload with `material_externo = true` and `material_externo_detalle` empty/missing
- WHEN the backend validates Step 4
- THEN the backend rejects the request with a validation error
- AND nothing is persisted

### Scenario: material_externo true with detalle provided is accepted
- GIVEN a submit payload with `material_externo = true` and `material_externo_detalle = "Templete y sonido propios"`
- WHEN the backend validates Step 4
- THEN the validation passes

### Scenario: material_externo false does not require detalle
- GIVEN a submit payload with `material_externo = false` and `material_externo_detalle` empty/missing
- WHEN the backend validates Step 4
- THEN the validation passes (detalle is not required)

---

## Requirement: Legal acceptances required to submit (RN-014)

The system MUST reject the submit server-side unless BOTH `acepta_info_correcta_autorizacion` and `acepta_reglamento_y_aviso_privacidad` are `true`, regardless of client-side UI state.

### Scenario: Both acceptances true — submit proceeds
- GIVEN a submit payload with `acepta_info_correcta_autorizacion = true` and `acepta_reglamento_y_aviso_privacidad = true`
- AND all other validations pass
- WHEN the backend validates Step 5
- THEN the acceptance check passes and the submit proceeds to persistence

### Scenario: One acceptance false — submit rejected server-side
- GIVEN a submit payload with `acepta_info_correcta_autorizacion = true` and `acepta_reglamento_y_aviso_privacidad = false` (e.g. client-side disablement was bypassed via direct API call)
- WHEN the backend validates Step 5
- THEN the backend rejects the request with a validation error
- AND nothing is persisted

### Scenario: Both acceptances false or missing — submit rejected server-side
- GIVEN a submit payload with both acceptance fields `false` or absent
- WHEN the backend validates Step 5
- THEN the backend rejects the request with a validation error
- AND nothing is persisted

---

## Requirement: Multi-space / multi-day quote items with availability and pricing (RN-012)

The system MUST support multiple `QuoteItem`s per submission (multi-space and/or multi-day), check availability per item via existing `inventory` logic, compute pricing per item via existing `pricing` logic with correctly-typed calls (`target_date: date`, `duration_hours: Decimal`), aggregate the total, and reject the entire submission if any item is unavailable.

### Scenario: All items available — submit persists with aggregate total
- GIVEN a submit payload with 3 QuoteItems (different spaces and/or dates), all available in `inventory`
- WHEN the backend processes the submit
- THEN availability is checked per item via `inventory.check_single_availability` / `check_group_availability`
- AND price is computed per item via `pricing.calculate_price` (or `get_quote_for_space`) called with `target_date: date` and `duration_hours: Decimal`
- AND the Quote's total reflects the aggregate of all 3 items' computed prices
- AND 3 QuoteItem rows are persisted, all linked to the same Quote

### Scenario: One item unavailable — entire submit fails, nothing persisted
- GIVEN a submit payload with 3 QuoteItems, where 1 of them is no longer available (conflicting booking/hold)
- WHEN the backend processes the submit
- THEN the submit fails atomically
- AND NO Quote, QuoteItem, Lead, QuoteAdditionalService, or quote_wizard_details row is persisted for this attempt (verify via DB query / rollback)
- AND the response identifies that at least one item is unavailable

### Scenario: Pricing call uses correct types, not the broken create_quote pattern
- GIVEN a submit payload with a valid QuoteItem (space_id, fecha, hora_inicio, hora_fin)
- WHEN the backend computes `cotizacion_calculada` for that item
- THEN the pricing call passes `target_date` as a `date` object and `duration_hours` as a `Decimal` (not raw `datetime` objects, and not silently caught and defaulted to a caller-supplied `precio` via a broad `except`)
- AND the computed price reflects the actual pricing engine result, not a fallback default

---

## Requirement: Atomic persistence and traceability on successful submit (RN-013)

On successful submit, the system MUST atomically persist a Lead (requester data, not a user account), a Quote with a unique `portal_folio`, QuoteItem(s), QuoteAdditionalService(s), and a `quote_wizard_details` row.

### Scenario: Successful submit persists all linked records
- GIVEN a solicitante completes all 5 steps with a valid, still-`quotation_in_progress` folio, valid field data, availability confirmed, and both legal acceptances true
- WHEN the solicitante submits
- THEN a Lead row is created with the requester's Step 3 data (nombre_completo, correo_institucional, telefono_contacto, etc.)
- AND a Quote row is created with `portal_folio` set to the validated folio value
- AND one or more QuoteItem rows are created, linked to the Quote
- AND QuoteAdditionalService rows are created for each selected `servicios_apoyo` entry (zero rows if none selected)
- AND a `quote_wizard_details` row is created (1:1 with the Quote), holding Step 1/3/4 wizard-specific fields and the legal acceptance flags

### Scenario: portal_folio uniqueness is enforced
- GIVEN a Quote already exists in Hub with `portal_folio = "BCE-20260715-172822-2973"`
- WHEN a second submit attempt (e.g. duplicate/replay) tries to persist a new Quote with the same `portal_folio`
- THEN the persistence layer rejects the duplicate (unique constraint violation surfaced as a controlled error)
- AND no duplicate Quote is created

### Scenario: No user account is created for the requester
- GIVEN a solicitante completes and submits the wizard successfully
- WHEN the submission is persisted
- THEN no `User` record (of any role, including `CUSTOMER`) is created for the requester
- AND the requester's identity exists only as Lead data, not as an authenticatable account

---

## Requirement: Best-effort, non-blocking confirmation email (RN-016)

After a successful submit, the system MUST attempt to send a confirmation email to `correo_institucional`; email failure MUST NOT fail the submit, and the confirmation screen MUST be shown regardless of email outcome.

### Scenario: Email succeeds — confirmation screen shown
- GIVEN a submit has been successfully persisted
- WHEN the system attempts to send the confirmation email to `correo_institucional`
- AND the email send succeeds
- THEN the solicitante is shown the confirmation screen with the recepción / revisión ≤ 24 h hábiles message

### Scenario: Email send fails — submit still succeeds and confirmation screen is shown
- GIVEN a submit has been successfully persisted
- WHEN the system attempts to send the confirmation email to `correo_institucional`
- AND the email send raises an exception (e.g. SMTP failure)
- THEN the submit response still reports success (the exception is caught, not propagated to fail the request)
- AND the failure is logged
- AND the solicitante is shown the confirmation screen with the recepción / revisión ≤ 24 h hábiles message
- AND no `NotificationLog` row is written for this event (RN-016 does not use `NotificationLog`, since it FKs reservations, not quotes)

---

## Requirement: Public, no-login access with tenant resolution (RN-002, config)

All folio gate and wizard submit endpoints MUST be public (no JWT required), with `tenant_id` resolved from `settings.DEFAULT_TENANT_ID` (or the existing catalog fallback), not from an authenticated session.

### Scenario: Gate endpoint accessible without any Authorization header
- GIVEN no `Authorization` header is sent
- WHEN a request is made to the folio gate endpoint with a valid folio
- THEN the request is processed normally (not rejected as unauthenticated)

### Scenario: Submit endpoint accessible without any Authorization header
- GIVEN no `Authorization` header is sent
- WHEN a request is made to the wizard submit endpoint with a complete, valid payload
- THEN the request is processed normally (not rejected as unauthenticated)

### Scenario: Tenant resolved from DEFAULT_TENANT_ID configuration
- GIVEN `settings.DEFAULT_TENANT_ID` is configured to a specific tenant
- WHEN a public gate or submit request is processed
- THEN the `tenant_id` used for availability checks, pricing, and persistence resolves to that configured tenant (or its existing catalog fallback), not from any session/JWT claim

---

## Requirement: Documents step retains existing functional behavior (RN-015)

Step 3's document upload MUST retain the existing MIME/size/versioning rules already implemented, with no functional change beyond adaptation into the wizard.

### Scenario: Existing document validation rules still apply in the wizard
- GIVEN a solicitante attempts to upload a document in Step 3 that violates existing MIME-type or size rules
- WHEN the upload is processed
- THEN it is rejected with the same validation behavior as the current `booking/confirm/page.tsx` upload flow (no new/loosened/tightened rule introduced by this change)

---

## Risks / Assumptions carried into spec

- Legal copy URLs (Reglamento / Aviso de Privacidad) are env-configurable placeholders; the spec does not test their content, only that both checkboxes gate submission (RN-014).
- Portal gate auth (API key/HMAC) is assumed not required for MVP per proposal's stated assumption; if added, scenarios above still hold since it is a config-driven header on the same client wrapper.
- `status_post_envio` uses the existing default initial Quote status; no new state machine value is introduced or tested here beyond the `portal_folio` link.
