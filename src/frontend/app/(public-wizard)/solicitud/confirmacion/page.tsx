'use client';

/**
 * Wizard confirmation screen (REQ-012 §4, RN-016). Shown regardless of
 * `email_sent` — email is best-effort and never blocks the submit. Resets
 * the wizard store now that the flow is complete.
 */

import { Suspense, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { CheckCircle2 } from 'lucide-react';

import { useQuoteWizardStore } from '@/features/quote-wizard';

function SolicitudConfirmacionContent() {
  const searchParams = useSearchParams();
  const reset = useQuoteWizardStore((s) => s.reset);

  const total = searchParams.get('total');
  const emailSent = searchParams.get('email_sent') === 'true';

  useEffect(() => {
    reset();
    // Reset once, on mount — the wizard flow is complete at this point.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="max-w-md w-full bg-white rounded-xl shadow-sm border border-gray-200 p-8 text-center">
        <div className="flex justify-center mb-6">
          <div className="w-14 h-14 rounded-full bg-emerald-100 flex items-center justify-center">
            <CheckCircle2 className="w-8 h-8 text-emerald-600" />
          </div>
        </div>
        <h1 className="text-xl font-bold text-gray-900 mb-2">Solicitud enviada</h1>
        <p className="text-sm text-gray-600 mb-4">
          Recibimos tu solicitud de cotización correctamente. Nuestro equipo la revisará en un plazo de hasta 24
          horas hábiles y te contactaremos con los siguientes pasos.
        </p>
        {total && (
          <p className="text-sm text-gray-500 mb-4">
            Total preliminar de tu solicitud: <span className="font-semibold text-gray-900">${total}</span>
          </p>
        )}
        {!emailSent && (
          <p className="text-xs text-gray-400">
            No pudimos confirmar el envío del correo de confirmación, pero tu solicitud quedó registrada
            correctamente.
          </p>
        )}
      </div>
    </div>
  );
}

export default function SolicitudConfirmacionPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
          <p className="text-sm text-gray-500">Cargando confirmación...</p>
        </div>
      }
    >
      <SolicitudConfirmacionContent />
    </Suspense>
  );
}
