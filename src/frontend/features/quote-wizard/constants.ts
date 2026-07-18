/**
 * Frozen enum catalog values for the public quote-request wizard (REQ-012 §4).
 * MUST match `TipoEvento` / `CaracterEvento` in `src/backend/app/modules/crm/models.py`
 * verbatim — these are the values persisted, not just display labels.
 */

export const TIPO_EVENTO_OPTIONS = [
  'Firma de convenio',
  'Conferencia',
  'Taller / Workshop',
  'Presentación',
  'Networking',
  'Rueda de prensa',
  'Reunión institucional',
  'Otro',
] as const;

export const CARACTER_EVENTO_OPTIONS = [
  'Público',
  'Privado',
  'Gubernamental',
  'Académico',
  'Empresarial',
] as const;

export const TIPO_EVENTO_OTRO = 'Otro';

/** RN-006: descripcion_evento word limit. */
export const DESCRIPCION_EVENTO_MAX_WORDS = 300;

export const TOTAL_WIZARD_STEPS = 5;
