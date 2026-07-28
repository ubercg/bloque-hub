# Portal Gate Integration Specification

## Purpose

Defines the outbound HMAC-signed contract between Hub and BLOQUE Portal: canonical
string construction, signature computation, error-code-driven state resolution, and
the RN-012 retry policy. Covers `portal_gate/signing.py`, the `httpx.Auth` subclass,
`client.py`, and the local test double `portal-mock.py`.

Established by REQ-013 (`req-013-portal-hmac`), which closed RISK-4: REQ-012
(`quote-request-folio`) had shipped the Portal gate against an *assumed* contract
(public route, no auth, root-level `status` field). This domain replaces that
assumption entirely with the real, confirmed contract below.

## Requirements

### Requirement: Integration route only

Hub MUST consume exclusively
`GET {PORTAL_API_BASE_URL}/api/integrations/bloque-hub/leads/{folio}/access`. The old
assumed public route `/api/public/space-event-requests/access/{folio}` MUST NOT be
reachable from any code path, including the gate, the submit revalidation, transport
retries, and signature re-fires.

#### Scenario: Gate calls the integration route
- GIVEN a folio gate request
- WHEN Hub calls Portal
- THEN the request targets
  `GET {PORTAL_API_BASE_URL}/api/integrations/bloque-hub/leads/{folio}/access`

#### Scenario: Submit revalidation calls the same route
- GIVEN a submit revalidation request
- WHEN Hub calls Portal
- THEN the request targets the same integration route as the gate, not the old
  public route

#### Scenario: Old public route is never invoked
- GIVEN any code path in `portal_gate`
- WHEN Hub calls Portal
- THEN `/api/public/space-event-requests/access/{folio}` is never constructed or
  requested

### Requirement: Retirement of the legacy API key

`PORTAL_API_KEY` and the `X-Api-Key` header MUST be fully retired from code and
configuration; neither MUST appear anywhere after this change.

#### Scenario: Setting removed from configuration
- GIVEN the application configuration after this change
- WHEN inspected
- THEN no `PORTAL_API_KEY` setting exists

#### Scenario: Header never sent
- GIVEN any outbound request to Portal
- WHEN the request is built
- THEN it never includes an `X-Api-Key` header

### Requirement: Credential configuration per environment

`PORTAL_HUB_API_KEY` and `PORTAL_HUB_API_SECRET` MUST be read from configuration or
the secrets manager, with no default values present in the repository. Each
environment MUST use its own distinct pair; staging and production MUST NOT share
one.

#### Scenario: No repository defaults
- GIVEN the repository's configuration source and version-controlled files
- WHEN inspected
- THEN neither setting has a default value defined in the repository

#### Scenario: Both settings required to start
- GIVEN the application starts without either setting configured
- WHEN startup is attempted
- THEN the application fails to start rather than falling back to an implicit value
  or deferring the failure to the first request

#### Scenario: Staging and production do not share a pair
- GIVEN the staging and production environments
- WHEN their configured credential pairs are compared
- THEN they are distinct, never the same key/secret combination

### Requirement: Canonical string construction

The system MUST build the canonical string as exactly `METHOD + "\n" + PATH + "\n" +
TIMESTAMP`, where `PATH` excludes scheme, host, port, and query string, and is
byte-identical to the path transmitted on the wire.

#### Scenario: Query string excluded from canonical string
- GIVEN a signed request whose URL carries a query string
- WHEN the canonical string is built
- THEN the query string is absent from `PATH`

#### Scenario: Signed path matches wire path
- GIVEN a request built by the HTTP client
- WHEN the auth layer reads the path to sign
- THEN it reads the path after client-side normalization, byte-identical to what is
  transmitted

#### Scenario: Timestamp format
- GIVEN a signed request
- WHEN `X-Bloque-Timestamp` is generated
- THEN it is Unix seconds in UTC, expressed as a digits-only string

### Requirement: HMAC signature computation

The system MUST compute the signature as
`base64(hmac_sha256_raw(secret, canonical_string))`.

#### Scenario: Known vector
- GIVEN a fixed secret, method, path, and timestamp
- WHEN the signature is computed
- THEN it equals the precomputed expected value

### Requirement: Fresh signature per attempt

The system MUST generate a new timestamp and signature for every attempt, including
retries and the RN-012 re-fire.

#### Scenario: No signature reuse across attempts
- GIVEN two consecutive attempts for the same logical request
- WHEN both are inspected
- THEN their timestamps and signatures differ

### Requirement: 401 retry policy

The system MUST NOT retry `MISSING_CREDENTIALS`, `UNKNOWN_API_KEY`,
`INVALID_SIGNATURE`, or `MALFORMED_TIMESTAMP`. It MUST retry `TIMESTAMP_EXPIRED`
exactly once, with a freshly signed request, and this re-fire MUST NOT consume a
transport retry slot.

#### Scenario: Deterministic auth failures never retried
- GIVEN a 401 response with `error_code` in {MISSING_CREDENTIALS, UNKNOWN_API_KEY,
  INVALID_SIGNATURE, MALFORMED_TIMESTAMP}
- WHEN the client processes it
- THEN it resolves to `INTEGRATION_AUTH_FAILURE` without a second attempt

#### Scenario: Timestamp expiry re-fires once
- GIVEN a 401 with `error_code = TIMESTAMP_EXPIRED`
- WHEN the client processes it
- THEN it re-signs and re-sends exactly one more request

#### Scenario: Re-fire does not consume transport retry budget
- GIVEN a `TIMESTAMP_EXPIRED` re-fire
- WHEN `PORTAL_RETRY_ATTEMPTS` is evaluated afterward
- THEN the re-fire did not decrement it

#### Scenario: Worst case is two HTTP requests
- GIVEN a `TIMESTAMP_EXPIRED` response followed by any 401
- WHEN the call completes
- THEN at most two HTTP requests were made and the result is
  `INTEGRATION_AUTH_FAILURE`

### Requirement: Status parsing from `data.status`

The system MUST read eligibility from `data.status == "quotation_in_progress"` and
MUST NOT read `status` at the JSON root or infer eligibility from HTTP status alone.

#### Scenario: Eligible folio
- GIVEN a `200` response with `data.status = "quotation_in_progress"`
- WHEN parsed
- THEN the folio resolves to `ELIGIBLE`

#### Scenario: Ineligible folio
- GIVEN a `200` response with a different `data.status` value
- WHEN parsed
- THEN the folio resolves to `NOT_ELIGIBLE`

#### Scenario: Missing status is a contract violation, not a rejection
- GIVEN a `200` response with no `data.status` key
- WHEN parsed
- THEN it resolves to `UNAVAILABLE`, is logged with marker
  `portal_gate.contract_violation` and the response's keys (never values), and is
  never `NOT_ELIGIBLE`

### Requirement: `status_label` is diagnostic-only

`data.status_label` MUST be recorded in diagnostic logs alongside the resolved
`error_code`. It MUST NOT be propagated to any Hub API response intended for
rendering, because Portal's copy carries no stability contract — the same reason
RN-010 forbids parsing `message`.

#### Scenario: status_label appears in diagnostic logs
- GIVEN a Portal response that includes `data.status_label`
- WHEN Hub logs the outcome
- THEN the log entry includes `status_label` alongside `error_code`

#### Scenario: status_label is not propagated for rendering
- GIVEN a Portal response that includes `data.status_label`
- WHEN Hub builds any API response
- THEN `status_label` is not included as display copy; Hub's own copy is used

### Requirement: Error-code taxonomy

The system MUST map every documented HTTP status / `error_code` pair to its
`PortalFolioStatus`.

#### Scenario: 401 variants map to auth failure
- GIVEN a 401 with any of the five documented `error_code` values
- WHEN mapped
- THEN the result is `INTEGRATION_AUTH_FAILURE`

#### Scenario: 403 and 404 map to not eligible
- GIVEN a `403` with `error_code` `NOT_ELIGIBLE` or `TERMINAL`, or a `404` with
  `FOLIO_NOT_FOUND`
- WHEN mapped
- THEN the result is `NOT_ELIGIBLE` with no retry

#### Scenario: 429 and 5xx/timeout map to unavailable
- GIVEN a `429`, a `5xx`, or a timeout
- WHEN mapped
- THEN the result is `UNAVAILABLE` and the transport retry loop applies

### Requirement: Secret hygiene

The system MUST NOT expose `PORTAL_HUB_API_SECRET` in the frontend bundle, API
responses, or the repository, and MUST NOT log the secret, `X-Bloque-Signature`, or
the canonical string. It MUST log `error_code`, the public `api_key`, the truncated
folio, and latency.

#### Scenario: Signing happens only in the backend
- GIVEN any signed request
- WHEN its origin is inspected
- THEN the signature was computed in Hub's backend process, never in browser code

#### Scenario: Secret never reaches the frontend or the repository
- GIVEN the built frontend bundle, every Hub API response, and the repository
- WHEN each is inspected for `PORTAL_HUB_API_SECRET`
- THEN the secret appears in none of them

#### Scenario: Sensitive fields excluded from logs
- GIVEN a logged auth failure
- WHEN the log entry is inspected
- THEN it contains `error_code`, `api_key`, truncated folio, and latency, and never
  the secret, signature, or canonical string

### Requirement: Test double verifies signatures

`portal-mock.py` MUST reject requests with an invalid signature or missing auth
headers, so it cannot reintroduce RISK-4.

#### Scenario: Bad signature rejected
- GIVEN a request signed with an incorrect secret
- WHEN the double receives it
- THEN it responds `401 INVALID_SIGNATURE`

#### Scenario: Missing headers rejected
- GIVEN a request with no `X-Bloque-*` headers
- WHEN the double receives it
- THEN it responds `401 MISSING_CREDENTIALS`

## Notes

- **Known open item (WARNING-1, unresolved at archive time):** whether the shared
  edge proxy in front of this stack (outside this repository) preserves `502`
  responses unmodified (`proxy_intercept_errors`) has not been confirmed. If it
  intercepts, flip `PORTAL_AUTH_FAILURE_HTTP_STATUS` (currently `502`, in
  `api/portal_gate_http.py`) to `503` and the matching frontend fallback row. See
  `req-013-portal-hmac`'s archive report.
- **RN-020 (per-environment credential pairs):** only one live pair exists as of
  archive time (used for the connected smoke against production). A second,
  distinct pair for a dedicated staging environment is required if/when staging
  exists apart from production — tracked as an open operational item, not a code
  defect.
