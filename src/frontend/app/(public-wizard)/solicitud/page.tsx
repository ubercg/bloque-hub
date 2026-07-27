'use client';

/**
 * Folio gate screen — public entry point for the "Solicitud de Cotización" wizard (REQ-012).
 * Anonymous access (no auth header). Validates the BLOQUE Portal folio via
 * POST /api/public/quote-requests/validate-folio before unlocking the wizard.
 */

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ShieldCheck } from 'lucide-react';

import apiClient from '@/lib/http/apiClient';
import { useQuoteWizardStore } from '@/features/quote-wizard';

const FOLIO_PLACEHOLDER = 'BCE-YYYYMMDD-HHMMSS-RRRR';
/** Mirrors RN-017 server-side format check; client-side hint only, server is authoritative. */
const FOLIO_FORMAT_HINT = /^BCE-\d{8}-\d{6}-\d{4}$/;

const RN003_MESSAGE =
  'El folio proporcionado no se encuentra disponible para iniciar una cotización. Verifica el estatus en BLOQUE Portal.';
const INVALID_FORMAT_MESSAGE = 'El formato de folio ingresado no es válido. Verifica el folio e intenta de nuevo.';
const UNAVAILABLE_MESSAGE = 'El servicio de validación no está disponible en este momento. Intenta de nuevo más tarde.';
const GENERIC_ERROR_MESSAGE = 'Ocurrió un error al validar el folio. Intenta de nuevo.';

export default function SolicitudGatePage() {
  const router = useRouter();
  const setFolio = useQuoteWizardStore((s) => s.setFolio);
  const setGateStatus = useQuoteWizardStore((s) => s.setGateStatus);
  const gateStatus = useQuoteWizardStore((s) => s.gateStatus);
  const gateErrorMessage = useQuoteWizardStore((s) => s.gateErrorMessage);

  const [folioInput, setFolioInput] = useState('');
  const isLoading = gateStatus === 'loading';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedFolio = folioInput.trim();
    setFolio(trimmedFolio);
    setGateStatus('loading');

    // FOLIO_FORMAT_HINT is a client-side hint only (RN-017); the server is the
    // authoritative validator and returns 422 for malformed folios.
    try {
      await apiClient.post('/public/quote-requests/validate-folio', { folio: trimmedFolio });
      setGateStatus('unlocked');
      router.push('/solicitud/wizard');
    } catch (err: unknown) {
      const status =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { status?: number } }).response?.status
          : undefined;

      if (status === 422) {
        setGateStatus('invalid_format', INVALID_FORMAT_MESSAGE);
      } else if (status === 403) {
        setGateStatus('not_eligible', RN003_MESSAGE);
      } else if (status === 503) {
        setGateStatus('unavailable', UNAVAILABLE_MESSAGE);
      } else {
        setGateStatus('not_eligible', GENERIC_ERROR_MESSAGE);
      }
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="max-w-md w-full bg-white rounded-xl shadow-sm border border-gray-200 p-8">
        <div className="flex justify-center mb-6">
          <div className="w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center">
            <ShieldCheck className="w-6 h-6 text-blue-600" />
          </div>
        </div>
        <h1 className="text-xl font-bold text-center text-gray-900 mb-2">
          Solicitud de cotización
        </h1>
        <p className="text-sm text-gray-500 text-center mb-6">
          Ingresa el folio de tu solicitud en BLOQUE Portal para continuar.
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label htmlFor="folio" className="block text-sm font-medium text-gray-700 mb-1">
              Folio
            </label>
            <input
              id="folio"
              name="folio"
              type="text"
              autoComplete="off"
              required
              value={folioInput}
              onChange={(e) => setFolioInput(e.target.value)}
              placeholder={FOLIO_PLACEHOLDER}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono"
            />
          </div>

          {gateStatus !== 'idle' && gateStatus !== 'loading' && gateStatus !== 'unlocked' && gateErrorMessage && (
            <div
              role="alert"
              className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2"
            >
              {gateErrorMessage}
            </div>
          )}

          <button
            type="submit"
            disabled={isLoading}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? 'Validando folio...' : 'Continuar'}
          </button>
        </form>
      </div>
    </div>
  );
}
