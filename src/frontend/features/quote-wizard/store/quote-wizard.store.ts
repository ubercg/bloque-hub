/**
 * Quote Wizard (Solicitud de Cotización) state management with Zustand.
 * Single source of truth for the public 5-step wizard, gated by a BLOQUE
 * Portal folio. Mirrors `event-cart.store.ts` conventions (no RHF/Zod).
 * REQ-012.
 */

import { create } from 'zustand';

/** Step 2 line item: one space + one date/time slot (multi-space/multi-day). */
export interface WizardItem {
  spaceId: string;
  fecha: string; // YYYY-MM-DD
  horaInicio: string; // HH:mm
  horaFin: string; // HH:mm
  /** Result of the availability + pricing preview call (advisory; server recomputes at submit). */
  cotizacionCalculada?: number;
}

/** Step 4 selection: one servicio de apoyo + quantity. */
export interface ServiceSelection {
  serviceId: string;
  quantity: number;
}

export type WizardStep = 1 | 2 | 3 | 4 | 5;

export interface QuoteWizardState {
  // Gate (folio validation, before step 1)
  folio: string;
  folioUnlocked: boolean;
  gateStatus: 'idle' | 'loading' | 'unlocked' | 'not_eligible' | 'invalid_format' | 'unavailable';
  gateErrorMessage: string | null;

  // Step 1 — Evento
  tipoEvento: string;
  nombreEvento: string;
  caracterEvento: string;
  descripcionEvento: string;
  asistentesEstimados: number;
  habraPrensa: boolean;

  // Step 2 — Espacio / fecha / cotización (multi-item)
  items: WizardItem[];

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
  serviciosApoyo: ServiceSelection[];
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
  setGateStatus: (
    status: QuoteWizardState['gateStatus'],
    errorMessage?: string | null
  ) => void;
  setStep: (step: WizardStep) => void;
  addItem: (item: WizardItem) => void;
  removeItem: (index: number) => void;
  addServiceSelection: (service: ServiceSelection) => void;
  removeServiceSelection: (serviceId: string) => void;
  goNext: () => void;
  goBack: () => void;
  reset: () => void;
}

const initialState = {
  folio: '',
  folioUnlocked: false,
  gateStatus: 'idle' as const,
  gateErrorMessage: null,

  tipoEvento: '',
  nombreEvento: '',
  caracterEvento: '',
  descripcionEvento: '',
  asistentesEstimados: 0,
  habraPrensa: false,

  items: [] as WizardItem[],

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

  serviciosApoyo: [] as ServiceSelection[],
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
      folioUnlocked: status === 'unlocked',
      gateErrorMessage: status === 'unlocked' ? null : errorMessage,
    }),

  setStep: (step) => set({ currentStep: step }),

  addItem: (item) => set((state) => ({ items: [...state.items, item] })),

  removeItem: (index) =>
    set((state) => ({ items: state.items.filter((_, i) => i !== index) })),

  addServiceSelection: (service) =>
    set((state) => {
      const exists = state.serviciosApoyo.some((s) => s.serviceId === service.serviceId);
      if (exists) {
        return {
          serviciosApoyo: state.serviciosApoyo.map((s) =>
            s.serviceId === service.serviceId ? service : s
          ),
        };
      }
      return { serviciosApoyo: [...state.serviciosApoyo, service] };
    }),

  removeServiceSelection: (serviceId) =>
    set((state) => ({
      serviciosApoyo: state.serviciosApoyo.filter((s) => s.serviceId !== serviceId),
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
