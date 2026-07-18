/**
 * Client-side step guards (UX only — server re-validates everything,
 * design.md §6.4). Plain derived functions, no memoization (React Compiler).
 */

import { DESCRIPCION_EVENTO_MAX_WORDS, TIPO_EVENTO_OTRO } from './constants';
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
