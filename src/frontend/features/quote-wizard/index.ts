export {
  useQuoteWizardStore,
  type QuoteWizardState,
  type WizardItem,
  type ServiceSelection,
  type WizardStep,
} from './store/quote-wizard.store';

export { StepEvento } from './components/StepEvento';
export { StepEspacio } from './components/StepEspacio';
export { StepSolicitante } from './components/StepSolicitante';
export { StepServicios } from './components/StepServicios';
export { StepResumen } from './components/StepResumen';
export { DocumentUpload } from './components/DocumentUpload';

export {
  isStepEventoValid,
  isStepEspacioValid,
  isStepSolicitanteValid,
  isStepServiciosValid,
  isStepResumenValid,
  countWords,
} from './validation';

export { TOTAL_WIZARD_STEPS, LEGAL_REGLAMENTO_URL, LEGAL_AVISO_PRIVACIDAD_URL } from './constants';
