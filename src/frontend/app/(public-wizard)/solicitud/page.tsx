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
import {
  GATE_STATUS,
  readGateError,
  resolveGateFailure,
  useQuoteWizardStore,
  type LeadPrefill,
} from '@/features/quote-wizard';

const FOLIO_PLACEHOLDER = 'BCE-YYYYMMDD-HHMMSS-RRRR';
/** Mirrors RN-017 server-side format check; client-side hint only, server is authoritative. */
const FOLIO_FORMAT_HINT = /^BCE-\d{8}-\d{6}-\d{4}$/;

interface ValidateFolioResponse {
  lead_prefill?: LeadPrefill | null;
}

export default function SolicitudGatePage() {
  const router = useRouter();
  const setFolio = useQuoteWizardStore((s) => s.setFolio);
  const setGateStatus = useQuoteWizardStore((s) => s.setGateStatus);
  const hydrateFromPrefill = useQuoteWizardStore((s) => s.hydrateFromPrefill);
  const gateStatus = useQuoteWizardStore((s) => s.gateStatus);
  const gateErrorMessage = useQuoteWizardStore((s) => s.gateErrorMessage);

  const [folioInput, setFolioInput] = useState('');
  const isLoading = gateStatus === GATE_STATUS.LOADING;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedFolio = folioInput.trim();
    setFolio(trimmedFolio);
    setGateStatus(GATE_STATUS.LOADING);

    // FOLIO_FORMAT_HINT is a client-side hint only (RN-017); the server is the
    // authoritative validator and returns 422 for malformed folios.
    try {
      const res = await apiClient.post<ValidateFolioResponse>('/public/quote-requests/validate-folio', {
        folio: trimmedFolio,
      });
      // Hydration runs BEFORE unlock + navigation so Step 3 mounts already filled.
      if (res.data.lead_prefill) {
        hydrateFromPrefill(res.data.lead_prefill);
      }
      setGateStatus(GATE_STATUS.UNLOCKED);
      router.push('/solicitud/wizard');
    } catch (err: unknown) {
      const { status, reason } = readGateError(err);
      const [nextStatus, message] = resolveGateFailure(status, reason);
      setGateStatus(nextStatus, message);
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

          {gateStatus !== GATE_STATUS.IDLE &&
            gateStatus !== GATE_STATUS.LOADING &&
            gateStatus !== GATE_STATUS.UNLOCKED &&
            gateErrorMessage && (
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
