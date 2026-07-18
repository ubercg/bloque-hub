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

export const SECTOR_OPTIONS = [
  'Gobierno municipal/estatal/federal',
  'Universidad / Institución educativa',
  'Empresa privada',
  'Organismo internacional',
  'Organización civil',
  'Startup / Emprendimiento',
  'Otro',
] as const;

export const SECTOR_OTRO = 'Otro';

export const COMO_CONOCISTE_OPTIONS = [
  'Recomendación de otra institución',
  'Redes sociales',
  'Sitio web del Municipio',
  'Ya he realizado eventos anteriores',
  'Otro',
] as const;

export const COMO_CONOCISTE_OTRO = 'Otro';

export const MONTAJE_REQUERIDO_OPTIONS = [
  'Estándar (mesas y sillas en U)',
  'Teatro',
  'Aula',
  'Cóctel',
  'Protocolar para firma',
  'Sin montaje',
] as const;

/** REQ-012 §4.4 — fixed informational note shown in Step 3 for gobierno/oficio requesters. */
export const OFICIO_GOBIERNO_NOTE =
  'Si tu institución requiere oficio para autorizar el evento, adjúntalo en la sección de documentos. El equipo de BLOQUE lo revisará junto con tu solicitud.';

/** RN-011: coordination notice shown when el solicitante indica material externo. */
export const MATERIAL_EXTERNO_NOTICE =
  'El montaje e ingreso de material externo debe coordinarse con el equipo de BLOQUE con al menos 48 horas de anticipación.';

/** RN-015 — same MIME/size messaging as `booking/confirm/page.tsx` (no rule change). */
export const DOCUMENT_ACCEPT = '.pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png';
export const DOCUMENT_MAX_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB, mirrors MAX_KYC_FILE_BYTES
export const DOCUMENT_SIZE_MESSAGE = 'Formatos: PDF, JPG o PNG (máx. 10 MB por archivo).';
export const DOCUMENT_TOO_LARGE_MESSAGE = 'El archivo supera el tamaño máximo permitido (10 MB).';
export const DOCUMENT_INVALID_TYPE_MESSAGE = 'Tipo de archivo no permitido. Usa PDF, JPG o PNG.';

/** RN-006: descripcion_evento word limit. */
export const DESCRIPCION_EVENTO_MAX_WORDS = 300;

export const TOTAL_WIZARD_STEPS = 5;

/**
 * Legal acceptance links (RN-014). Env-configurable placeholders (design §7);
 * define `NEXT_PUBLIC_LEGAL_REGLAMENTO_URL` / `NEXT_PUBLIC_LEGAL_AVISO_PRIVACIDAD_URL`
 * in `.env` before `docker compose build frontend` (inyectadas en build time),
 * mirroring the backend's `LEGAL_REGLAMENTO_URL` / `LEGAL_AVISO_PRIVACIDAD_URL`.
 */
export const LEGAL_REGLAMENTO_URL =
  process.env.NEXT_PUBLIC_LEGAL_REGLAMENTO_URL || 'https://bloque.example/reglamento';
export const LEGAL_AVISO_PRIVACIDAD_URL =
  process.env.NEXT_PUBLIC_LEGAL_AVISO_PRIVACIDAD_URL || 'https://bloque.example/aviso-privacidad';
