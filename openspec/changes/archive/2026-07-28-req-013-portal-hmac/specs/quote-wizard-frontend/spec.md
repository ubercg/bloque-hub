# Quote Wizard Frontend Error States Specification

## Purpose

Defines how `solicitud/page.tsx` and the wizard store react to gate results: the
distinct `INTEGRATION_AUTH_FAILURE` state and its messaging, the fallback for
unrecognized errors (fixing the pre-existing `not_eligible` mislabeling defect at
`page.tsx:60-61`), and the store's prefill hydration action.

## Requirements

### Requirement: Distinct auth-failure state

The system MUST render `INTEGRATION_AUTH_FAILURE` as a system-fault message with no
call to action, distinct from both the folio-not-eligible message and the
Portal-unavailable message.

#### Scenario: Auth failure renders system-fault copy
- GIVEN a gate response carrying the auth-failure `detail.reason`
- WHEN the page renders
- THEN it shows a system-fault message with no retry or "check your folio" call to
  action

#### Scenario: Distinct from folio-not-eligible and Portal-unavailable
- GIVEN the three gate error states rendered in sequence
- WHEN their messages are compared
- THEN the auth-failure, not-eligible, and Portal-unavailable messages are all
  textually distinct

### Requirement: Unknown reason fallback

An absent or unrecognized `detail.reason` MUST fall back to a new `unknown_error`
state and MUST NOT fall back to `not_eligible`.

#### Scenario: Unrecognized reason does not become a folio rejection
- GIVEN a gate error response whose `detail.reason` is absent or not one of the
  known values
- WHEN the page processes it
- THEN `gateStatus` is set to `unknown_error`, never `not_eligible`

### Requirement: Store hydration from prefill

The wizard store MUST expose a bulk hydrate action that populates Step 3 (and the
referenced Step 1 / Step 2 informational fields) from a successful gate's
`lead_prefill`.

#### Scenario: Successful gate hydrates the store
- GIVEN a gate response with `lead_prefill`
- WHEN the page receives it
- THEN the store's hydrate action is invoked and Step 3 fields reflect the prefill
  values

### Requirement: Portal copy is never displayed

`data.status_label` MUST NOT be displayed to the Solicitante in any gate state
(RN-010). All applicant-facing copy MUST come from Hub's own constants.

#### Scenario: status_label never reaches the applicant
- GIVEN any applicant-facing gate state — unlocked, not-eligible, auth-failure,
  Portal-unavailable, or unknown-error
- WHEN the state renders
- THEN no text originating from Portal's `status_label` appears on screen; the
  rendered copy comes from Hub's own message constants
