/**
 * Client-side step guards (UX only — server re-validates everything,
 * design.md §6.4). Plain derived functions, no memoization (React Compiler).
 */

import { COMO_CONOCISTE_OTRO, DESCRIPCION_EVENTO_MAX_WORDS, SECTOR_OTRO, TIPO_EVENTO_OTRO } from './constants';
import type { QuoteWizardState, WizardItem } from './store/quote-wizard.store';

export function countWords(text: string): number {
  return text.trim().length === 0 ? 0 : text.trim().split(/\s+/).length;
}

type StepEventoFields = Pick<
  QuoteWizardState,
  'tipoEvento' | 'caracterEvento' | 'nombreEvento' | 'asistentesEstimados' | 'descripcionEvento'
>;

/** Step 1 — Evento (RN-006, RN-007, RN-008). */
export function isStepEventoValid(state: StepEventoFields): boolean {
  if (!state.tipoEvento || !state.caracterEvento) return false;
  if (state.tipoEvento === TIPO_EVENTO_OTRO && state.nombreEvento.trim().length === 0) return false;
  if (state.asistentesEstimados <= 0) return false;
  if (countWords(state.descripcionEvento) > DESCRIPCION_EVENTO_MAX_WORDS) return false;
  return true;
}

/** Step 2 — Espacio/fecha/cotización (RN-012): at least one item, each priced. */
export function isStepEspacioValid(items: WizardItem[]): boolean {
  if (items.length === 0) return false;
  return items.every((item) => typeof item.cotizacionCalculada === 'number');
}

type StepSolicitanteFields = Pick<
  QuoteWizardState,
  | 'nombreCompleto'
  | 'correoInstitucional'
  | 'telefonoContacto'
  | 'sector'
  | 'sectorOtro'
  | 'comoConociste'
  | 'comoConocisteOtro'
>;

/** Step 3 — Solicitante y documentos (RN-009, RN-010). */
export function isStepSolicitanteValid(state: StepSolicitanteFields): boolean {
  if (state.nombreCompleto.trim().length === 0) return false;
  if (state.correoInstitucional.trim().length === 0) return false;
  if (state.telefonoContacto.trim().length === 0) return false;
  if (!state.sector) return false;
  if (state.sector === SECTOR_OTRO && state.sectorOtro.trim().length === 0) return false;
  if (!state.comoConociste) return false;
  if (state.comoConociste === COMO_CONOCISTE_OTRO && state.comoConocisteOtro.trim().length === 0) return false;
  return true;
}

type StepServiciosFields = Pick<
  QuoteWizardState,
  'montajeRequerido' | 'materialExterno' | 'materialExternoDetalle'
>;

/** Step 4 — Servicios y montaje (RN-011). */
export function isStepServiciosValid(state: StepServiciosFields): boolean {
  if (!state.montajeRequerido) return false;
  if (state.materialExterno && state.materialExternoDetalle.trim().length === 0) return false;
  return true;
}

type StepResumenFields = Pick<QuoteWizardState, 'aceptaInfoCorrecta' | 'aceptaReglamento'>;

/** Step 5 — Resumen y aceptaciones (RN-014): submit disabled until both are true. */
export function isStepResumenValid(state: StepResumenFields): boolean {
  return state.aceptaInfoCorrecta === true && state.aceptaReglamento === true;
}
