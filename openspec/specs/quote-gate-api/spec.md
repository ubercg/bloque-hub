# Quote Gate API Specification

## Purpose

Defines the public API surface Hub exposes to a solicitante starting a public quote
request: the folio format check, the folio gate that unlocks the wizard, submit-time
revalidation, and no-login access. Originally established by REQ-012
(`quote-request-folio`); extended by REQ-013 (`req-013-portal-hmac`) with the
exhaustive status-to-HTTP mapping and the `lead_prefill` contract.

## Requirements

### Requirement: Folio format validation (RN-017)

The system MUST validate the folio format `BCE-YYYYMMDD-HHMMSS-RRRR` on the backend before calling the BLOQUE Portal API.

#### Scenario: Well-formed folio passes format check
- GIVEN a solicitante submits folio `BCE-20260715-172822-2973` to the gate endpoint
- WHEN the backend validates its format
- THEN the format check passes and the backend proceeds to call the BLOQUE Portal API

#### Scenario: Malformed folio is rejected before any Portal call
- GIVEN a solicitante submits a folio that does not match `BCE-YYYYMMDD-HHMMSS-RRRR` (e.g. `ABC-123`, empty string, or a folio missing segments)
- WHEN the gate endpoint validates the format
- THEN the backend returns a validation error WITHOUT calling the Portal API
- AND no outbound HTTP request to Portal is made (verifiable via mock/spy in tests)

### Requirement: Folio gate — Portal status validation (RN-001, RN-002, RN-003)

The system MUST call the BLOQUE Portal API to confirm the folio's status is `quotation_in_progress` before unlocking the wizard, and MUST block with a distinct reason otherwise. (How Hub authenticates and addresses that outbound call is defined by the `portal-gate-integration` domain; this requirement covers Hub's gate behavior toward the solicitante.)

#### Scenario: Valid folio in quotation_in_progress unlocks the wizard
- GIVEN a folio with valid format that Portal reports as status `quotation_in_progress`
- WHEN the solicitante submits the folio to the public gate endpoint
- THEN the endpoint returns `200` with a payload indicating the wizard is unlocked
- AND no authentication (JWT) is required for this call

#### Scenario: Folio not found is blocked with RN-003 message
- GIVEN a folio with valid format that Portal reports as not found
- WHEN the solicitante submits the folio to the gate endpoint
- THEN the endpoint returns a blocked response with the RN-003 message: "El folio proporcionado no se encuentra disponible para iniciar una cotización. Verifica el estatus en BLOQUE Portal."
- AND the wizard does NOT unlock

#### Scenario: Folio with wrong/terminal status is blocked with RN-003 message
- GIVEN a folio with valid format that Portal reports as a status other than `quotation_in_progress` (e.g. `quotation_sent`, `closed`, `rejected`)
- WHEN the solicitante submits the folio to the gate endpoint
- THEN the endpoint returns a blocked response with the RN-003 message
- AND the wizard does NOT unlock

#### Scenario: Access denied by Portal is blocked with RN-003 message
- GIVEN a folio with valid format that Portal reports as access denied
- WHEN the solicitante submits the folio to the gate endpoint
- THEN the endpoint returns a blocked response with the RN-003 message
- AND the wizard does NOT unlock

### Requirement: Portal client resilience — timeout/5xx retry and distinct error taxonomy

The Portal gate HTTP client MUST retry transient failures with backoff and surface a distinct "Portal unavailable" error, separate from "folio invalid/wrong status", when retries are exhausted.

#### Scenario: Transient timeout is retried then succeeds
- GIVEN the Portal API times out on the first call for a given folio but succeeds on a subsequent retry
- WHEN the gate endpoint calls the Portal client
- THEN the client retries with backoff
- AND if a retry succeeds, the gate proceeds using that successful response

#### Scenario: Portal unavailable after exhausting retries returns a distinct error
- GIVEN the Portal API times out or returns 5xx on every attempt (retries exhausted)
- WHEN the gate endpoint calls the Portal client
- THEN the endpoint returns an error distinct from the RN-003 "folio invalid/wrong status" message
- AND this error is distinguishable in the response (different error code/type) from the RN-003 block response
- AND the wizard does NOT unlock

### Requirement: Revalidation on submit (RN-004)

The system MUST revalidate the folio against Portal at submit time (Step 5) and reject the submission — persisting nothing — if the folio is no longer `quotation_in_progress`.

#### Scenario: Folio still valid at submit — request persists
- GIVEN a solicitante completed all 5 wizard steps with a folio that was `quotation_in_progress` at gate time
- AND the folio is still `quotation_in_progress` when Hub revalidates at submit
- WHEN the solicitante submits the wizard
- THEN Hub persists the Lead, Quote, QuoteItem(s), QuoteAdditionalService(s), and quote_wizard_details row
- AND the response confirms success

#### Scenario: Folio status changed before submit — nothing persists
- GIVEN a solicitante completed all 5 wizard steps with a folio that was `quotation_in_progress` at gate time
- AND by the time of submit, Portal now reports the folio's status as something else (e.g. `quotation_sent`) or not found
- WHEN the solicitante submits the wizard
- THEN the submit is rejected with a controlled error
- AND NO Lead, Quote, QuoteItem, QuoteAdditionalService, or quote_wizard_details row is created (verify via DB query / rollback)

#### Scenario: Portal unavailable at submit-time revalidation
- GIVEN a solicitante completed all 5 wizard steps
- AND Portal is unavailable (timeout/5xx exhausted retries) when Hub attempts revalidation at submit
- WHEN the solicitante submits the wizard
- THEN the submit is rejected with the distinct "Portal unavailable" error
- AND NO records are persisted

### Requirement: Public, no-login access with tenant resolution (RN-002, config)

All folio gate and wizard submit endpoints MUST be public (no JWT required), with `tenant_id` resolved from `settings.DEFAULT_TENANT_ID` (or the existing catalog fallback), not from an authenticated session.

#### Scenario: Gate endpoint accessible without any Authorization header
- GIVEN no `Authorization` header is sent
- WHEN a request is made to the folio gate endpoint with a valid folio
- THEN the request is processed normally (not rejected as unauthenticated)

#### Scenario: Submit endpoint accessible without any Authorization header
- GIVEN no `Authorization` header is sent
- WHEN a request is made to the wizard submit endpoint with a complete, valid payload
- THEN the request is processed normally (not rejected as unauthenticated)

#### Scenario: Tenant resolved from DEFAULT_TENANT_ID configuration
- GIVEN `settings.DEFAULT_TENANT_ID` is configured to a specific tenant
- WHEN a public gate or submit request is processed
- THEN the `tenant_id` used for availability checks, pricing, and persistence resolves to that configured tenant (or its existing catalog fallback), not from any session/JWT claim

### Requirement: Exhaustive status-to-HTTP mapping

The system MUST map every `PortalFolioStatus` member to an explicit HTTP response
via one shared helper used by both the gate and submit-revalidation call sites. An
unmapped member MUST fail loudly rather than default to `403 FOLIO_NOT_ELIGIBLE`.

#### Scenario: Every known status maps explicitly
- GIVEN each defined `PortalFolioStatus` member
- WHEN the mapping helper is invoked
- THEN it returns a defined HTTP status and `error_code`, with no catch-all branch
  involved

#### Scenario: Unmapped status fails loudly
- GIVEN a `PortalFolioStatus` member with no entry in the mapping
- WHEN the mapping helper is invoked
- THEN it raises rather than silently returning `403 FOLIO_NOT_ELIGIBLE`

#### Scenario: Gate and submit share the mapping
- GIVEN the same `PortalFolioStatus` result
- WHEN produced at the gate endpoint and at submit revalidation
- THEN both call sites resolve to the identical HTTP status and `error_code` via the
  same helper

### Requirement: `lead_prefill` exposure scope

`FolioValidateResponse.lead_prefill` MUST be returned only on a successful gate
response for the folio being queried, and MUST NOT appear on any error response, on
the submit endpoint, or in logs.

#### Scenario: Present only on a successful gate
- GIVEN a folio that resolves to `ELIGIBLE`
- WHEN the gate endpoint responds
- THEN `lead_prefill` is present in the response body

#### Scenario: Absent on error responses
- GIVEN a folio that resolves to `NOT_ELIGIBLE`, `INTEGRATION_AUTH_FAILURE`, or
  `UNAVAILABLE`
- WHEN the gate endpoint responds
- THEN `lead_prefill` is absent from the body and from any log line

### Requirement: `comentarios` truncation at the prefill boundary

The system MUST truncate `lead_prefill.comentarios` to `requerimientos_especiales`'s
validation cap (`schemas.py:193`), referencing a single shared constant, before it
leaves Hub's API, appending a Hub-authored marker counted within the cap.

#### Scenario: Comentarios exceeding the cap is truncated
- GIVEN a `comentarios` value longer than the 5000-character cap
- WHEN mapped to `lead_prefill`
- THEN the mapped value, including the truncation marker, is at or under the cap and
  the form remains submittable

#### Scenario: Truncation is logged without content
- GIVEN a truncated `comentarios`
- WHEN the truncation occurs
- THEN a `portal_gate.prefill_truncated` log entry records the folio and the
  original length, never the text

#### Scenario: Comentarios under the cap is unchanged
- GIVEN a `comentarios` value under the cap
- WHEN mapped
- THEN it is passed through without truncation or marker

### Requirement: Prefill hydration tolerates null keys

The system MUST hydrate all present `lead_prefill` keys and MUST treat any `null`
value, including `tipo_evento_sugerido = null`, as a normal case that does not block
hydration or log as an error.

#### Scenario: Complete prefill hydrates all fields
- GIVEN a `lead_prefill` with every key populated
- WHEN mapped to Step 3
- THEN all corresponding fields are populated

#### Scenario: Null keys degrade gracefully
- GIVEN a `lead_prefill` with `tipo_evento_sugerido = null` and other null keys
- WHEN mapped
- THEN those fields are left empty, no error is raised, and nothing is logged as an
  error

### Requirement: Field-specific mapping constraints

`comentarios` MUST map only to `requerimientos_especiales`. `fecha_tentativa` MUST
NOT preselect a Step 2 item. `espacio_requerido` MUST NOT resolve a `space_id`. All
prefilled fields MUST remain editable.

#### Scenario: Comentarios never reaches descripcion_evento
- GIVEN a `lead_prefill.comentarios` value
- WHEN mapped
- THEN it populates `requerimientos_especiales` and `descripcion_evento` is
  untouched by prefill

#### Scenario: Fecha tentativa stays informational
- GIVEN a `lead_prefill.fecha_tentativa` value
- WHEN the wizard loads
- THEN no Step 2 item is preselected from it

#### Scenario: Espacio requerido stays informational
- GIVEN a `lead_prefill.espacio_requerido` value
- WHEN the wizard loads
- THEN no `space_id` is derived or preselected from it

#### Scenario: Prefilled fields remain editable
- GIVEN any field hydrated from `lead_prefill`
- WHEN the Solicitante edits it
- THEN the new value is accepted like any manually entered value

## Notes

- **Merge provenance:** the first 5 requirements above (Folio format validation
  through Public no-login access) were established by REQ-012
  (`quote-request-folio`, archived 2026-07-28). The last 5 (Exhaustive
  status-to-HTTP mapping through Field-specific mapping constraints) were ADDED by
  REQ-013 (`req-013-portal-hmac`, archived 2026-07-28, same session). No REQ-012
  requirement was modified or removed by this merge; both sets are complementary
  and share no requirement names.
- **RISK-4 closure:** REQ-012 shipped this domain against an *assumed* Portal
  response shape (root-level `status` field). REQ-013 confirmed the real contract
  (`data.status`, mandatory HMAC, integration route) and closed RISK-4 — see the
  `portal-gate-integration` domain for the outbound call contract. None of the
  requirements above needed rewriting: they describe Hub's gate/submit behavior
  toward the solicitante, which did not change: no-login access, the RN-003
  message, and RN-004 revalidation all remain exactly as REQ-012 defined them.
- The "Portal client resilience" requirement's generic "Portal unavailable" error
  is now realized concretely as `PortalFolioStatus.UNAVAILABLE` mapped via the
  "Exhaustive status-to-HTTP mapping" requirement above.
