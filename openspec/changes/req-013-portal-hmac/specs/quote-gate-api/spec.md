# Quote Gate API Specification

## Purpose

Defines the public API surface (`api/public.py`, `crm/schemas.py`) that consumes
`portal_gate` results: the exhaustive status-to-HTTP mapping shared by the gate and
submit-revalidation endpoints (RN-016), and the `lead_prefill` contract exposed to
the frontend, including character-cap truncation (D3).

## Requirements

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
