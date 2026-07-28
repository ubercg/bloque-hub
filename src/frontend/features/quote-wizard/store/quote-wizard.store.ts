/**
 * Quote Wizard (Solicitud de Cotización) state management with Zustand.
 * Single source of truth for the public 5-step wizard, gated by a BLOQUE
 * Portal folio. Mirrors `event-cart.store.ts` conventions (no RHF/Zod).
 * REQ-012.
 */

import { create } from 'zustand';

import { COMO_CONOCISTE_OPTIONS, TIPO_EVENTO_OPTIONS } from '../constants';

/** Step 2 line item: one space + one date/time slot (multi-space/multi-day). */
export interface WizardItem {
  spaceId: string;
  fecha: string; // YYYY-MM-DD
  horaInicio: string; // HH:mm
  horaFin: string; // HH:mm
  /** Result of the availability + pricing preview call (advisory; server recomputes at submit). */
  cotizacionCalculada?: number;
}

export type WizardStep = 1 | 2 | 3 | 4 | 5;

/**
 * Const-object + extracted-type pattern (TypeScript skill), so the gate state
 * list has one source of truth and is exhaustively checkable. REQ-013 design §7.
 */
export const GATE_STATUS = {
  IDLE: 'idle',
  LOADING: 'loading',
  UNLOCKED: 'unlocked',
  INVALID_FORMAT: 'invalid_format',
  NOT_ELIGIBLE: 'not_eligible',
  UNAVAILABLE: 'unavailable',
  AUTH_FAILURE: 'auth_failure',
  UNKNOWN_ERROR: 'unknown_error',
} as const;
export type GateStatus = (typeof GATE_STATUS)[keyof typeof GATE_STATUS];

/**
 * Wire shape of `FolioValidateResponse.lead_prefill` (backend `LeadPrefillOut`,
 * REQ-013 design §6) — snake_case, as received over the wire. `hydrateFromPrefill`
 * maps these into the store's camelCase fields.
 */
export interface LeadPrefill {
  nombre_completo: string | null;
  cargo_puesto: string | null;
  institucion_organizacion: string | null;
  correo_institucional: string | null;
  telefono_contacto: string | null;
  asistentes_estimados: number | null;
  fecha_tentativa: string | null;
  tipo_evento_sugerido: string | null;
  espacio_requerido: string | null;
  requerimientos_especiales: string | null;
  como_conociste_bloque: string | null;
}

export interface QuoteWizardState {
  // Gate (folio validation, before step 1)
  folio: string;
  folioUnlocked: boolean;
  gateStatus: GateStatus;
  gateErrorMessage: string | null;
  /** Raw prefill payload from the gate response (REQ-013 §5). Null before hydration. */
  leadPrefill: LeadPrefill | null;
  /** Step 2 reference-only display (RN-022) — never preselects a wizard item. */
  fechaTentativa: string | null;
  /** Step 2 reference-only display (RN-015) — never resolves a `space_id`. */
  espacioRequerido: string | null;

  // Step 1 — Evento
  tipoEvento: string;
  nombreEvento: string;
  caracterEvento: string;
  descripcionEvento: string;
  asistentesEstimados: number;
  habraPrensa: boolean;

  // Step 2 — Espacio / fecha / cotización (multi-item)
  items: WizardItem[];
  /** Optional discount from Detalle de Espacios (advisory; commercial confirms). */
  discountCode: string | null;
  discountAmount: number;

  // Step 3 — Solicitante y documentos
  nombreCompleto: string;
  cargoPuesto: string;
  institucionOrganizacion: string;
  sector: string;
  sectorOtro: string;
  correoInstitucional: string;
  telefonoContacto: string;
  responsableSitioNombre: string;
  responsableSitioTelefono: string;
  comoConociste: string;
  comoConocisteOtro: string;
  documents: Record<string, File | File[]>;

  // Step 4 — Servicios y montaje
  /** FIXED closed enum values (REQ-012 §4.5), NOT catalog IDs — see `SERVICIOS_APOYO`. */
  serviciosApoyo: string[];
  montajeRequerido: string;
  requerimientosEspeciales: string;
  materialExterno: boolean;
  materialExternoDetalle: string;

  // Step 5 — Resumen y aceptaciones
  aceptaInfoCorrecta: boolean;
  aceptaReglamento: boolean;

  // Navigation
  currentStep: WizardStep;

  // Actions
  setField: <K extends keyof QuoteWizardState>(key: K, value: QuoteWizardState[K]) => void;
  setFolio: (folio: string) => void;
  setGateStatus: (status: GateStatus, errorMessage?: string | null) => void;
  /** Bulk-hydrates Step 1/2/3 fields from a successful gate's `lead_prefill`, one `set()` call. */
  hydrateFromPrefill: (prefill: LeadPrefill) => void;
  setStep: (step: WizardStep) => void;
  addItem: (item: WizardItem) => void;
  removeItem: (index: number) => void;
  /** Remove by space+fecha+horario (stable across reorders). */
  removeItemBySlot: (item: Pick<WizardItem, 'spaceId' | 'fecha' | 'horaInicio' | 'horaFin'>) => void;
  /** Replace all Step-2 items (e.g. after contiguous package reprice). */
  setItems: (items: WizardItem[]) => void;
  toggleServicioApoyo: (servicio: string) => void;
  goNext: () => void;
  goBack: () => void;
  reset: () => void;
}

const initialState = {
  folio: '',
  folioUnlocked: false,
  gateStatus: GATE_STATUS.IDLE as GateStatus,
  gateErrorMessage: null as string | null,
  leadPrefill: null as LeadPrefill | null,
  fechaTentativa: null as string | null,
  espacioRequerido: null as string | null,

  tipoEvento: '',
  nombreEvento: '',
  caracterEvento: '',
  descripcionEvento: '',
  asistentesEstimados: 0,
  habraPrensa: false,

  items: [] as WizardItem[],
  discountCode: null as string | null,
  discountAmount: 0,

  nombreCompleto: '',
  cargoPuesto: '',
  institucionOrganizacion: '',
  sector: '',
  sectorOtro: '',
  correoInstitucional: '',
  telefonoContacto: '',
  responsableSitioNombre: '',
  responsableSitioTelefono: '',
  comoConociste: '',
  comoConocisteOtro: '',
  documents: {} as Record<string, File | File[]>,

  serviciosApoyo: [] as string[],
  montajeRequerido: '',
  requerimientosEspeciales: '',
  materialExterno: false,
  materialExternoDetalle: '',

  aceptaInfoCorrecta: false,
  aceptaReglamento: false,

  currentStep: 1 as WizardStep,
};

export const useQuoteWizardStore = create<QuoteWizardState>((set) => ({
  ...initialState,

  setField: (key, value) => set({ [key]: value } as Pick<QuoteWizardState, typeof key>),

  setFolio: (folio) => set({ folio }),

  setGateStatus: (status, errorMessage = null) =>
    set({
      gateStatus: status,
      folioUnlocked: status === GATE_STATUS.UNLOCKED,
      gateErrorMessage: status === GATE_STATUS.UNLOCKED ? null : errorMessage,
    }),

  hydrateFromPrefill: (prefill) =>
    set((state) => {
      const patch: Partial<QuoteWizardState> = { leadPrefill: prefill };

      // RN-013: only non-null incoming values are written. A `null` leaves the
      // current value untouched — re-hydration cannot clobber text the
      // applicant already typed.
      if (prefill.nombre_completo !== null) patch.nombreCompleto = prefill.nombre_completo;
      if (prefill.cargo_puesto !== null) patch.cargoPuesto = prefill.cargo_puesto;
      if (prefill.institucion_organizacion !== null) {
        patch.institucionOrganizacion = prefill.institucion_organizacion;
      }
      if (prefill.correo_institucional !== null) patch.correoInstitucional = prefill.correo_institucional;
      if (prefill.telefono_contacto !== null) patch.telefonoContacto = prefill.telefono_contacto;
      if (prefill.asistentes_estimados !== null) patch.asistentesEstimados = prefill.asistentes_estimados;
      if (prefill.requerimientos_especiales !== null) {
        patch.requerimientosEspeciales = prefill.requerimientos_especiales;
      }
      // RN-022 / RN-015: reference-only, never preselects a Step 2 item or a space_id.
      if (prefill.fecha_tentativa !== null) patch.fechaTentativa = prefill.fecha_tentativa;
      if (prefill.espacio_requerido !== null) patch.espacioRequerido = prefill.espacio_requerido;

      // RN-014: a non-member of the closed enum is dropped silently, not an error.
      if (
        prefill.tipo_evento_sugerido !== null &&
        (TIPO_EVENTO_OPTIONS as readonly string[]).includes(prefill.tipo_evento_sugerido)
      ) {
        patch.tipoEvento = prefill.tipo_evento_sugerido;
      }
      if (
        prefill.como_conociste_bloque !== null &&
        (COMO_CONOCISTE_OPTIONS as readonly string[]).includes(prefill.como_conociste_bloque)
      ) {
        patch.comoConociste = prefill.como_conociste_bloque;
      }

      // RN-021 made structural on the frontend too: descripcionEvento is
      // never a hydration target — it is intentionally absent from `patch`.
      return { ...state, ...patch };
    }),

  setStep: (step) => set({ currentStep: step }),

  addItem: (item) =>
    set((state) => {
      const exists = state.items.some(
        (i) =>
          i.spaceId === item.spaceId &&
          i.fecha === item.fecha &&
          i.horaInicio === item.horaInicio &&
          i.horaFin === item.horaFin
      );
      if (exists) return state;
      return { items: [...state.items, item] };
    }),

  removeItem: (index) =>
    set((state) => ({ items: state.items.filter((_, i) => i !== index) })),

  removeItemBySlot: (slot) =>
    set((state) => ({
      items: state.items.filter(
        (i) =>
          !(
            i.spaceId === slot.spaceId &&
            i.fecha === slot.fecha &&
            i.horaInicio === slot.horaInicio &&
            i.horaFin === slot.horaFin
          )
      ),
    })),

  setItems: (items) => set({ items }),

  toggleServicioApoyo: (servicio) =>
    set((state) => ({
      serviciosApoyo: state.serviciosApoyo.includes(servicio)
        ? state.serviciosApoyo.filter((s) => s !== servicio)
        : [...state.serviciosApoyo, servicio],
    })),

  goNext: () =>
    set((state) => ({
      currentStep: (state.currentStep < 5 ? state.currentStep + 1 : state.currentStep) as WizardStep,
    })),

  goBack: () =>
    set((state) => ({
      currentStep: (state.currentStep > 1 ? state.currentStep - 1 : state.currentStep) as WizardStep,
    })),

  reset: () => set(initialState),
}));
