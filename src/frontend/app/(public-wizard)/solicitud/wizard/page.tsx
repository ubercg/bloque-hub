'use client';

/**
 * Public wizard shell (REQ-012 §4). Single client page driving the 5 steps
 * from the Zustand store (design.md §6.1/§6.3). Steps 3-5 ship in PR#7b;
 * this PR (#7a) implements the shell + steps 1-2.
 */

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useShallow } from 'zustand/react/shallow';

import { StepEspacio, StepEvento, TOTAL_WIZARD_STEPS, useQuoteWizardStore } from '@/features/quote-wizard';
import { isStepEspacioValid, isStepEventoValid } from '@/features/quote-wizard';

const STEP_LABELS = ['Evento', 'Espacio', 'Solicitante', 'Servicios', 'Resumen'];

export default function SolicitudWizardPage() {
  const router = useRouter();
  const folioUnlocked = useQuoteWizardStore((s) => s.folioUnlocked);
  const currentStep = useQuoteWizardStore((s) => s.currentStep);
  const goNext = useQuoteWizardStore((s) => s.goNext);
  const goBack = useQuoteWizardStore((s) => s.goBack);
  const stepEventoFields = useQuoteWizardStore(
    useShallow((s) => ({
      tipoEvento: s.tipoEvento,
      caracterEvento: s.caracterEvento,
      nombreEvento: s.nombreEvento,
      asistentesEstimados: s.asistentesEstimados,
      descripcionEvento: s.descripcionEvento,
    }))
  );
  const items = useQuoteWizardStore((s) => s.items);

  useEffect(() => {
    if (!folioUnlocked) {
      router.replace('/solicitud');
    }
  }, [folioUnlocked, router]);

  if (!folioUnlocked) {
    return null;
  }

  const canAdvance =
    currentStep === 1
      ? isStepEventoValid(stepEventoFields)
      : currentStep === 2
        ? isStepEspacioValid(items)
        : false; // steps 3-5 land in PR#7b

  return (
    <div className="min-h-screen bg-gray-50 px-4 py-10">
      <div className="max-w-2xl mx-auto bg-white rounded-xl shadow-sm border border-gray-200 p-8">
        <ol className="flex items-center justify-between mb-8">
          {STEP_LABELS.map((label, idx) => {
            const stepNumber = idx + 1;
            const isActive = stepNumber === currentStep;
            const isDone = stepNumber < currentStep;
            return (
              <li key={label} className="flex-1 flex flex-col items-center gap-1">
                <span
                  className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium ${
                    isActive
                      ? 'bg-blue-600 text-white'
                      : isDone
                        ? 'bg-blue-100 text-blue-700'
                        : 'bg-gray-100 text-gray-400'
                  }`}
                >
                  {stepNumber}
                </span>
                <span className="text-xs text-gray-500 text-center">{label}</span>
              </li>
            );
          })}
        </ol>

        {currentStep === 1 && <StepEvento />}
        {currentStep === 2 && <StepEspacio />}
        {currentStep >= 3 && (
          <p className="text-sm text-gray-500">Este paso estará disponible próximamente.</p>
        )}

        <div className="flex justify-between mt-8">
          <button
            type="button"
            onClick={goBack}
            disabled={currentStep === 1}
            className="px-4 py-2 rounded-lg border border-gray-300 text-gray-700 font-medium hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Atrás
          </button>
          <button
            type="button"
            onClick={goNext}
            disabled={!canAdvance || currentStep === TOTAL_WIZARD_STEPS}
            className="px-4 py-2 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Siguiente
          </button>
        </div>
      </div>
    </div>
  );
}
