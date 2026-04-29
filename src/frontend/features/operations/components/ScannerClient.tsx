'use client';

import React, { useState, useEffect } from 'react';
import { validateQrCode } from '@/app/(operations)/scanner/actions';

export default function ScannerClient() {
  const [scannedData, setScannedData] = useState<string>('');
  const [validationResult, setValidationResult] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // In a real app, you would integrate a QR scanner library here like react-qr-reader
  // For this implementation, we simulate it with an input field
  const handleSimulateScan = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!scannedData) return;

    setLoading(true);
    setError(null);
    setValidationResult(null);

    try {
      const result = await validateQrCode(scannedData);
      setValidationResult(result);
    } catch (err) {
      console.error('Error validating QR:', err);
      setError('Ocurrió un error al procesar el código QR. Intente nuevamente.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md bg-white p-6 rounded-xl shadow-bloque-sm">
      <div className="mb-6 border-2 border-dashed border-gray-300 rounded-lg h-64 flex flex-col items-center justify-center bg-gray-50">
        <svg xmlns="http://www.w3.org/2000/svg" className="h-16 w-16 text-gray-400 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h4M4 12h4m12 0h.01M5 8h2a1 1 0 001-1V5a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1zm12 0h2a1 1 0 001-1V5a1 1 0 00-1-1h-2a1 1 0 00-1 1v2a1 1 0 001 1zM5 20h2a1 1 0 001-1v-2a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1z" />
        </svg>
        <p className="text-gray-500 font-medium">Cámara activada</p>
        <p className="text-sm text-gray-400">Apunte el código QR aquí</p>
      </div>

      <div className="mb-6">
        <h3 className="text-sm font-semibold text-gray-700 mb-2 uppercase tracking-wider">Simulador Manual</h3>
        <form onSubmit={handleSimulateScan} className="flex gap-2">
          <input 
            type="text" 
            value={scannedData}
            onChange={(e) => setScannedData(e.target.value)}
            placeholder="Ingrese JWT del ticket..."
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-bloque-primary-500 outline-none"
          />
          <button 
            type="submit"
            disabled={loading || !scannedData}
            className="px-4 py-2 bg-bloque-primary-600 text-white rounded-lg font-medium hover:bg-bloque-primary-700 disabled:opacity-50 transition-colors"
          >
            {loading ? '...' : 'Validar'}
          </button>
        </form>
      </div>

      {error && (
        <div className="p-4 mb-4 bg-red-50 text-red-700 border-l-4 border-red-500 rounded-r-lg">
          <p className="font-semibold">Error</p>
          <p className="text-sm">{error}</p>
        </div>
      )}

      {validationResult && (
        <div className={`p-4 rounded-lg border ${validationResult.allowed ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
          <div className="flex items-center gap-3 mb-2">
            {validationResult.allowed ? (
              <svg xmlns="http://www.w3.org/00/svg" className="h-8 w-8 text-green-500" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
            ) : (
              <svg xmlns="http://www.w3.org/00/svg" className="h-8 w-8 text-red-500" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
            )}
            <div>
              <h3 className={`text-lg font-bold ${validationResult.allowed ? 'text-green-800' : 'text-red-800'}`}>
                {validationResult.allowed ? 'ACCESO PERMITIDO' : 'ACCESO DENEGADO'}
              </h3>
            </div>
          </div>
          
          <div className="mt-4 space-y-2 text-sm text-gray-700 bg-white/50 p-3 rounded">
            <p><strong>Razón:</strong> {validationResult.reason}</p>
            {validationResult.details && (
              <>
                <p><strong>Evento:</strong> {validationResult.details.event_name || 'N/A'}</p>
                <p><strong>Asistente:</strong> {validationResult.details.attendee_name || 'N/A'}</p>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}