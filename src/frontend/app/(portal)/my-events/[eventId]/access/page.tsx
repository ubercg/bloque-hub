'use client';

/**
 * Portal: Acceso y factura — Readiness, descarga de QR y CFDI
 */

import { useCallback, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import useSWR from 'swr';
import apiClient from '@/lib/http/apiClient';
import {
  Loader2,
  ArrowLeft,
  QrCode,
  FileText,
  CheckCircle,
  AlertCircle,
} from 'lucide-react';

interface Readiness {
  is_ready: boolean;
  checklist_pct: number;
  evidence_complete: boolean;
  details: {
    pending_critical_items: unknown[];
    pending_evidence: unknown[];
  };
}

interface CfdiDocument {
  id: string;
  reservation_id: string;
  tipo: string;
  uuid_fiscal: string | null;
  estado: string;
  monto: number;
  timbrado_at: string | null;
  error_codigo: string | null;
  error_descripcion: string | null;
  pdf_url?: string | null;
  xml_url?: string | null;
}

const fetcher = (url: string) => apiClient.get(url).then((res) => res.data);

export default function AccessPage() {
  const params = useParams();
  const eventId = (params?.eventId as string) ?? '';
  const [qrDownloading, setQrDownloading] = useState(false);

  const { data: readiness, error: readinessError } = useSWR<Readiness>(
    eventId ? `/reservations/${eventId}/readiness` : null,
    fetcher,
    { refreshInterval: 60000, revalidateOnFocus: true }
  );

  const { data: cfdiList } = useSWR<CfdiDocument[]>(
    eventId ? `/reservations/${eventId}/cfdi` : null,
    fetcher,
    { revalidateOnFocus: true }
  );

  const downloadQr = useCallback(async () => {
    if (!eventId || !readiness?.is_ready || qrDownloading) return;
    setQrDownloading(true);
    try {
      const res = await apiClient.get(`/access/reservations/${eventId}/qr`, {
        responseType: 'blob',
      });
      const blob = new Blob([res.data], { type: 'image/png' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `qr-acceso-${eventId.slice(0, 8)}.png`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // ignore
    } finally {
      setQrDownloading(false);
    }
  }, [eventId, readiness?.is_ready, qrDownloading]);

  const isReady = readiness?.is_ready === true;
  const readinessNotFound = readinessError && (readinessError as { response?: { status?: number } })?.response?.status === 404;
  const cfdiDocs = cfdiList ?? [];

  return (
    <div className="space-y-6 sm:space-y-8">
      <div>
        <Link
          href={`/my-events/${eventId}`}
          className="inline-flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-4 min-h-[44px] touch-manipulation"
        >
          <ArrowLeft className="w-4 h-4" />
          Volver al evento
        </Link>
        <h1 className="text-xl sm:text-2xl font-bold text-gray-900">Acceso y factura</h1>
        <p className="text-gray-600 text-sm sm:text-base">
          Estado de preparación, QR de entrada y facturación.
        </p>
      </div>

      {/* Readiness */}
      <section className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
        <h2 className="font-semibold text-gray-900 mb-4">Estado de preparación</h2>
        {readinessNotFound ? (
          <p className="text-gray-500 flex items-center gap-2">
            <AlertCircle className="w-5 h-5" />
            La orden de servicio se está preparando. Vuelve más tarde.
          </p>
        ) : readiness ? (
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              {isReady ? (
                <CheckCircle className="w-8 h-8 text-green-600" />
              ) : (
                <Loader2 className="w-8 h-8 text-amber-500" />
              )}
              <div>
                <div className="font-medium text-gray-900">
                  {isReady ? 'Tu evento está listo' : 'Preparando tu evento'}
                </div>
                <div className="text-sm text-gray-600">
                  Documentos del buzón: {readiness.evidence_complete ? 'completos' : 'pendientes'} · Preparación operativa: {Math.round(readiness.checklist_pct * 100)}%
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-2 text-gray-500">
            <Loader2 className="w-5 h-5 animate-spin" />
            Cargando estado...
          </div>
        )}
      </section>

      {/* QR */}
      <section className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
        <h2 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <QrCode className="w-5 h-5 flex-shrink-0" />
          QR de acceso
        </h2>
        {isReady ? (
          <div>
            <p className="text-gray-600 mb-4 text-sm sm:text-base">
              Descarga tu QR para mostrar en la entrada el día del evento.
            </p>
            <button
              type="button"
              onClick={downloadQr}
              disabled={qrDownloading}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 min-h-[44px] px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium touch-manipulation"
            >
              {qrDownloading ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <QrCode className="w-5 h-5" />
              )}
              Descargar QR
            </button>
          </div>
        ) : (
          <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg text-sm sm:text-base">
            <p className="text-amber-800 font-medium">
              Tu evento debe estar preparado (documentos aprobados y tareas listas) para descargar el QR.
            </p>
            <p className="text-sm text-amber-700 mt-1">
              Completa los documentos requeridos en la sección anterior y espera la revisión de operaciones.
            </p>
          </div>
        )}
      </section>

      {/* CFDI */}
      <section className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
        <h2 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <FileText className="w-5 h-5 flex-shrink-0" />
          Factura CFDI
        </h2>
        {cfdiDocs.length === 0 ? (
          <p className="text-gray-500 text-sm sm:text-base">
            Aún no hay factura asociada a esta reserva. Se generará tras la confirmación del pago.
          </p>
        ) : (
          <ul className="space-y-3">
            {cfdiDocs.map((doc) => (
              <li
                key={doc.id}
                className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-3 bg-gray-50 rounded-lg"
              >
                <div className="min-w-0">
                  <div className="font-medium text-gray-900 text-sm sm:text-base">
                    {doc.tipo} · ${doc.monto.toLocaleString('es-MX')} MXN
                  </div>
                  <div className="text-xs sm:text-sm text-gray-600">
                    {doc.estado === 'TIMBRADO' && doc.timbrado_at
                      ? `Timbrado el ${new Date(doc.timbrado_at).toLocaleDateString('es-MX', { timeZone: 'America/Mexico_City' })}`
                      : doc.estado === 'ERROR' && doc.error_descripcion
                        ? doc.error_descripcion
                        : doc.estado}
                  </div>
                </div>
                <div className="flex gap-2 flex-shrink-0">
                  {doc.estado === 'TIMBRADO' && doc.pdf_url && (
                    <a
                      href={doc.pdf_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="min-h-[44px] inline-flex items-center px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 touch-manipulation"
                    >
                      PDF
                    </a>
                  )}
                  {doc.estado === 'TIMBRADO' && doc.xml_url && (
                    <a
                      href={doc.xml_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="min-h-[44px] inline-flex items-center px-4 py-2 text-sm bg-gray-600 text-white rounded-lg hover:bg-gray-700 touch-manipulation"
                    >
                      XML
                    </a>
                  )}
                  {doc.estado === 'PENDIENTE' && (
                    <span className="text-sm text-gray-500 py-2">Pendiente de timbrado</span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
