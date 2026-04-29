'use client';

import { Suspense, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import apiClient from '@/lib/http/apiClient';

function UploadVoucherContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const reservationId = searchParams.get('id');

  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadSuccess, setUploadSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setError(null);

    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0];

      // Client-side validation (matches backend rules)
      const MIN_SIZE_KB = 5;
      const MAX_SIZE_KB = 10 * 1024; // 10 MB
      const fileSizeKB = selectedFile.size / 1024;

      if (fileSizeKB < MIN_SIZE_KB) {
        setError(`El archivo es muy pequeño (mínimo ${MIN_SIZE_KB}KB)`);
        return;
      }

      if (fileSizeKB > MAX_SIZE_KB) {
        setError(`El archivo es muy grande (máximo ${MAX_SIZE_KB}KB = 10MB)`);
        return;
      }

      // Validate file type
      const allowedTypes = ['application/pdf', 'image/jpeg', 'image/png', 'image/heic'];
      if (!allowedTypes.includes(selectedFile.type)) {
        setError('Tipo de archivo no permitido. Use PDF, JPG, PNG o HEIC');
        return;
      }

      setFile(selectedFile);
    }
  };

  const handleUpload = async () => {
    if (!file || !reservationId) return;

    setIsUploading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await apiClient.post(
        `/reservations/${reservationId}/upload_slip`,
        formData,
        {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        }
      );

      setUploadSuccess(true);

      // Redirect to reservation details after 2 seconds
      setTimeout(() => {
        router.push(`/my-events/${reservationId}`);
      }, 2000);
    } catch (err: any) {
      console.error('Error al subir comprobante:', err);
      const raw = err.response?.data?.detail;
      const msg = typeof raw === 'string' ? raw : Array.isArray(raw) ? raw.map((x: unknown) => (typeof x === 'object' && x && 'msg' in x ? (x as { msg: string }).msg : String(x))).join('. ') : null;

      if (err.response?.status === 409) {
        setError('Este archivo ya ha sido subido anteriormente (duplicado detectado)');
      } else if (err.response?.status === 400) {
        const text = msg || 'Error de validación';
        setError(
          text.includes('AWAITING_PAYMENT') || text.includes('solo en espera')
            ? `${text} Si tu reserva está en revisión, reconstruye el backend (docker compose build backend && docker compose up -d backend).`
            : text
        );
      } else {
        setError(msg || 'Error al subir el comprobante. Intenta nuevamente.');
      }
    } finally {
      setIsUploading(false);
    }
  };

  if (uploadSuccess) {
    return (
      <div className="max-w-md mx-auto p-8 text-center">
        <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
          <svg className="w-8 h-8 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <h2 className="text-2xl font-bold mb-2">¡Comprobante recibido!</h2>
        <p className="text-gray-600 mb-4">
          Tu reserva está protegida. El ejecutivo comercial revisará tu pago en menos de 2 horas hábiles.
        </p>
        <div className="text-sm text-gray-500">
          Redirigiendo a tu reserva...
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-md mx-auto p-8">
      <h1 className="text-3xl font-bold mb-4">Subir Comprobante de Pago</h1>
      <p className="text-gray-600 mb-8">
        Sube tu comprobante SPEI para completar tu reserva.
        Formatos permitidos: <strong>PDF, JPG, PNG, HEIC</strong> (máx. 10MB).
      </p>

      <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center hover:border-blue-400 transition">
        {file ? (
          <div className="space-y-4">
            <svg className="w-16 h-16 text-blue-600 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <div>
              <div className="font-medium">{file.name}</div>
              <div className="text-sm text-gray-500">
                {(file.size / 1024).toFixed(1)} KB
              </div>
            </div>
            <button
              onClick={() => setFile(null)}
              className="text-sm text-gray-500 hover:text-red-600"
            >
              Cambiar archivo
            </button>
          </div>
        ) : (
          <label className="cursor-pointer block">
            <svg className="w-16 h-16 text-gray-400 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <div className="text-gray-600 mb-2">Click para seleccionar archivo</div>
            <div className="text-sm text-gray-400">o arrastra y suelta aquí</div>
            <input
              type="file"
              className="hidden"
              accept=".pdf,.jpg,.jpeg,.png,.heic"
              onChange={handleFileChange}
            />
          </label>
        )}
      </div>

      {error && (
        <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {error}
        </div>
      )}

      {file && !error && (
        <button
          onClick={handleUpload}
          disabled={isUploading}
          className="w-full mt-6 bg-blue-600 text-white py-3 rounded-lg font-semibold hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition"
        >
          {isUploading ? (
            <span className="flex items-center justify-center">
              <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Subiendo...
            </span>
          ) : (
            'Confirmar y Subir'
          )}
        </button>
      )}

      <div className="mt-8 p-4 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-800">
        <strong>💡 Importante:</strong> Al subir tu comprobante, tu reserva quedará protegida
        y no expirará mientras el equipo revisa tu pago.
      </div>
    </div>
  );
}

export default function UploadVoucherPage() {
  return (
    <Suspense
      fallback={
        <div className="max-w-md mx-auto p-8 text-center text-gray-500">
          Cargando...
        </div>
      }
    >
      <UploadVoucherContent />
    </Suspense>
  );
}
