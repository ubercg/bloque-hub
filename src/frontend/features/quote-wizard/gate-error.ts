/**
 * Pure gate-failure resolution for the folio gate (`app/(public-wizard)/solicitud/page.tsx`).
 * REQ-013 design §7. Testable without rendering — no imports from `app/`.
 *
 * This is a convention, not an enforced rule: `.dependency-cruiser.cjs` has
 * exactly two rules (`app/` must not deep-import `features/*​/{components,store,lib}`,
 * and `lib/` must not import `features/`); neither constrains `features/ → app/`,
 * so `npm run verify:deps` will NOT catch a violation here.
 */

import { GATE_STATUS, type GateStatus } from './store/quote-wizard.store';

export interface GateError {
  status?: number;
  reason?: string;
}

/** Reads `{status, reason}` out of an axios-shaped error without assuming axios types. */
export function readGateError(err: unknown): GateError {
  if (!err || typeof err !== 'object' || !('response' in err)) {
    return {};
  }
  const response = (
    err as { response?: { status?: number; data?: { detail?: { reason?: string } } } }
  ).response;
  return {
    status: response?.status,
    reason: response?.data?.detail?.reason,
  };
}

export const INVALID_FORMAT_MESSAGE =
  'El formato de folio ingresado no es válido. Verifica el folio e intenta de nuevo.';
export const NOT_ELIGIBLE_MESSAGE =
  'El folio proporcionado no se encuentra disponible para iniciar una cotización. Verifica el estatus en BLOQUE Portal.';
export const UNAVAILABLE_MESSAGE =
  'El servicio de validación no está disponible en este momento. Intenta de nuevo más tarde.';
/**
 * D1 (frozen verbatim, design §7 / Phase 0.3): system fault, no call to
 * action, no claim that an alert was raised — there is no alerting per §2.3.
 */
export const AUTH_FAILURE_MESSAGE =
  'No pudimos validar tu folio por una falla de configuración en la integración con BLOQUE Portal. ' +
  'Reintentar no resolverá el problema.';
export const GENERIC_ERROR_MESSAGE = 'Ocurrió un error al validar el folio. Intenta de nuevo.';

/** `detail.reason` values the gate endpoint can send (design §5's `reason` column). */
const GATE_REASON_RESOLUTION: Record<string, [GateStatus, string]> = {
  INVALID_FOLIO_FORMAT: [GATE_STATUS.INVALID_FORMAT, INVALID_FORMAT_MESSAGE],
  FOLIO_NOT_ELIGIBLE: [GATE_STATUS.NOT_ELIGIBLE, NOT_ELIGIBLE_MESSAGE],
  PORTAL_UNAVAILABLE: [GATE_STATUS.UNAVAILABLE, UNAVAILABLE_MESSAGE],
  INTEGRATION_AUTH_FAILURE: [GATE_STATUS.AUTH_FAILURE, AUTH_FAILURE_MESSAGE],
};

/**
 * Precedence (design §7): `reason` match first (authoritative) → status-code
 * fallback → `UNKNOWN_ERROR` last. Never resolves to `NOT_ELIGIBLE` as a
 * fallback — that was the pre-existing `page.tsx:60-61` mislabeling defect.
 */
export function resolveGateFailure(status?: number, reason?: string): [GateStatus, string] {
  if (reason && reason in GATE_REASON_RESOLUTION) {
    return GATE_REASON_RESOLUTION[reason];
  }

  switch (status) {
    case 422:
      return [GATE_STATUS.INVALID_FORMAT, INVALID_FORMAT_MESSAGE];
    case 403:
      return [GATE_STATUS.NOT_ELIGIBLE, NOT_ELIGIBLE_MESSAGE];
    case 503:
      return [GATE_STATUS.UNAVAILABLE, UNAVAILABLE_MESSAGE];
    // Coupled to PORTAL_AUTH_FAILURE_HTTP_STATUS = 502 in
    // src/backend/app/api/portal_gate_http.py (design §5/§14, D1 fallback).
    // If that constant is ever flipped to 503, this row must move with it —
    // and the `503` row above would need to become `PORTAL_UNAVAILABLE`-only
    // again, since `reason` is authoritative in step 1 regardless.
    case 502:
      return [GATE_STATUS.AUTH_FAILURE, AUTH_FAILURE_MESSAGE];
    default:
      return [GATE_STATUS.UNKNOWN_ERROR, GENERIC_ERROR_MESSAGE];
  }
}
