'use client';

/**
 * Buzón de Evidencias: lista de requisitos y carga de archivos (drag & drop)
 * Tipos permitidos: PDF, JPG, PNG. Máximo 10 MB.
 */

import { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import useSWR from 'swr';
import { toast } from 'sonner';
import apiClient from '@/lib/http/apiClient';
import { Loader2, FileCheck, FileX, Upload, AlertCircle, Trash2, Download, ExternalLink } from 'lucide-react';
import { SkeletonListRow } from '@/components/ui/Skeleton';

const ACCEPTED = {
  'application/pdf': ['.pdf'],
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/png': ['.png'],
};
const MAX_SIZE = 10 * 1024 * 1024; // 10 MB

interface EvidenceRequirement {
  id: string;
  master_service_order_id: string;
  tipo_documento: string;
  estado: string;
  filename: string | null;
  file_size_bytes: number | null;
  uploaded_at: string | null;
  plazo_vence_at: string;
  revisado_at: string | null;
  motivo_rechazo: string | null;
  intentos_carga: number;
}

const fetcher = (url: string) => apiClient.get(url).then((res) => res.data);

const ESTADO_LABEL: Record<string, string> = {
  PENDIENTE: 'Pendiente',
  PENDIENTE_REVISION: 'En revisión',
  APROBADO: 'Aprobado',
  RECHAZADO: 'Rechazado',
};

function formatTipo(tipo: string): string {
  return tipo.replace(/_/g, ' ');
}

interface EvidenceUploaderProps {
  reservationId: string;
}

export default function EvidenceUploader({ reservationId }: EvidenceUploaderProps) {
  const [uploadingFor, setUploadingFor] = useState<string | null>(null);
  const [errorFor, setErrorFor] = useState<string | null>(null);

  const { data: requirements, mutate } = useSWR<EvidenceRequirement[]>(
    `/reservations/${reservationId}/evidence-requirements`,
    fetcher,
    { revalidateOnFocus: true }
  );

  const uploadFile = useCallback(
    async (tipoDocumento: string, file: File) => {
      setUploadingFor(tipoDocumento);
      setErrorFor(null);
      const formData = new FormData();
      formData.append('tipo_documento', tipoDocumento);
      formData.append('file', file);
      try {
        await apiClient.post(
          `/reservations/${reservationId}/evidence`,
          formData,
          {
            headers: { 'Content-Type': 'multipart/form-data' },
          }
        );
        await mutate();
        toast.success('Documento subido', {
          description: `${formatTipo(tipoDocumento)} se subió correctamente.`,
        });
      } catch (e: unknown) {
        const err = e as { response?: { data?: { detail?: string } } };
        const message = err.response?.data?.detail ?? 'Error al subir. Intenta de nuevo.';
        setErrorFor(message);
        toast.error('Error al subir', { description: message });
      } finally {
        setUploadingFor(null);
      }
    },
    [reservationId, mutate]
  );

  const deleteEvidence = useCallback(
    async (evidenceId: string) => {
      setErrorFor(null);
      try {
        await apiClient.delete(`/reservations/${reservationId}/evidence/${evidenceId}`);
        await mutate();
        toast.success('Documento eliminado', { description: 'Puedes subir otro cuando quieras.' });
      } catch (e: unknown) {
        const err = e as { response?: { data?: { detail?: string } } };
        const message = err.response?.data?.detail ?? 'Error al eliminar. Intenta de nuevo.';
        toast.error('Error al eliminar', { description: message });
      }
    },
    [reservationId, mutate]
  );

  const handleDownload = useCallback(
    async (evidenceId: string, filename: string | null) => {
      try {
        const { data } = await apiClient.get(
          `/reservations/${reservationId}/evidence/${evidenceId}/download`,
          { responseType: 'blob' }
        );
        const url = URL.createObjectURL(data as Blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename || 'documento.pdf';
        a.click();
        URL.revokeObjectURL(url);
      } catch {
        toast.error('Error al descargar');
      }
    },
    [reservationId]
  );

  const handleView = useCallback(
    async (evidenceId: string) => {
      try {
        const { data } = await apiClient.get(
          `/reservations/${reservationId}/evidence/${evidenceId}/download`,
          { responseType: 'blob' }
        );
        const url = URL.createObjectURL(data as Blob);
        window.open(url, '_blank', 'noopener');
        setTimeout(() => URL.revokeObjectURL(url), 60000);
      } catch {
        toast.error('Error al abrir el documento');
      }
    },
    [reservationId]
  );

  if (!requirements) {
    return (
      <ul className="space-y-0 border border-gray-200 rounded-lg divide-y divide-gray-100 bg-white overflow-hidden">
        {[1, 2, 3].map((i) => (
          <li key={i}>
            <SkeletonListRow />
          </li>
        ))}
      </ul>
    );
  }

  if (requirements.length === 0) {
    return (
      <p className="text-gray-500 text-sm">
        No hay documentos requeridos para este evento aún. Si operaciones los solicita, aparecerán aquí.
      </p>
    );
  }

  return (
    <ul className="space-y-4">
      {requirements.map((req) => {
        const canUpload =
          req.estado === 'PENDIENTE' ||
          req.estado === 'RECHAZADO' ||
          req.estado === 'PENDIENTE_REVISION';
        const canDelete =
          (req.estado === 'PENDIENTE_REVISION' || req.estado === 'RECHAZADO') &&
          !!req.filename;
        const isUploading = uploadingFor === req.tipo_documento;

        return (
          <li
            key={req.id}
            className="bg-gray-50 rounded-lg p-4 border border-gray-200"
          >
            <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
              <div className="min-w-0 flex-1">
                <div className="font-medium text-gray-900">
                  {formatTipo(req.tipo_documento)}
                </div>
                <div className="flex flex-wrap items-center gap-2 mt-1">
                  <span
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${
                      req.estado === 'APROBADO'
                        ? 'bg-green-100 text-green-800'
                        : req.estado === 'RECHAZADO'
                          ? 'bg-red-100 text-red-800'
                          : req.estado === 'PENDIENTE_REVISION'
                            ? 'bg-amber-100 text-amber-800'
                            : 'bg-gray-100 text-gray-700'
                    }`}
                  >
                    {req.estado === 'APROBADO' ? (
                      <FileCheck className="w-3.5 h-3.5" />
                    ) : req.estado === 'RECHAZADO' ? (
                      <FileX className="w-3.5 h-3.5" />
                    ) : null}
                    {ESTADO_LABEL[req.estado] ?? req.estado}
                  </span>
                  {req.filename && (
                    <span className="text-xs text-gray-500 truncate max-w-[180px]">
                      {req.filename}
                    </span>
                  )}
                </div>
                {req.estado === 'RECHAZADO' && req.motivo_rechazo && (
                  <p className="text-sm text-red-600 mt-2" role="alert">
                    {req.motivo_rechazo}
                  </p>
                )}
                {req.filename && (
                  <div className="flex flex-wrap gap-2 mt-2">
                    <button
                      type="button"
                      onClick={() => handleView(req.id)}
                      className="inline-flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800 font-medium min-h-[44px] min-w-[44px] touch-manipulation"
                      aria-label={`Ver ${formatTipo(req.tipo_documento)}`}
                    >
                      <ExternalLink className="w-4 h-4" />
                      Ver
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDownload(req.id, req.filename)}
                      className="inline-flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800 font-medium min-h-[44px] min-w-[44px] touch-manipulation"
                      aria-label={`Descargar ${formatTipo(req.tipo_documento)}`}
                    >
                      <Download className="w-4 h-4" />
                      Descargar
                    </button>
                    {canDelete && (
                      <button
                        type="button"
                        onClick={() => deleteEvidence(req.id)}
                        className="inline-flex items-center gap-1 text-sm text-red-600 hover:text-red-800 font-medium min-h-[44px] min-w-[44px] touch-manipulation"
                        aria-label={`Eliminar ${formatTipo(req.tipo_documento)} para subir otro`}
                      >
                        <Trash2 className="w-4 h-4" />
                        Eliminar
                      </button>
                    )}
                  </div>
                )}
              </div>

              {canUpload && (
                <DropZoneForRequirement
                  tipoDocumento={req.tipo_documento}
                  isUploading={isUploading}
                  onUpload={uploadFile}
                  onClearError={() => setErrorFor(null)}
                />
              )}
            </div>
            {errorFor && uploadingFor === req.tipo_documento && (
              <p className="mt-2 text-sm text-red-600 flex items-center gap-1" role="alert">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                {errorFor}
              </p>
            )}
          </li>
        );
      })}
    </ul>
  );
}

interface DropZoneForRequirementProps {
  tipoDocumento: string;
  isUploading: boolean;
  onUpload: (tipo: string, file: File) => void;
  onClearError: () => void;
}

function DropZoneForRequirement({
  tipoDocumento,
  isUploading,
  onUpload,
  onClearError,
}: DropZoneForRequirementProps) {
  const onDrop = useCallback(
    (accepted: File[], rejected: unknown[]) => {
      onClearError();
      if (accepted.length > 0) {
        onUpload(tipoDocumento, accepted[0]);
      }
    },
    [tipoDocumento, onUpload, onClearError]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED,
    maxSize: MAX_SIZE,
    maxFiles: 1,
    disabled: isUploading,
    onDropRejected: onClearError,
  });

  return (
    <div
      {...getRootProps()}
      className={`
        border-2 border-dashed rounded-lg p-4 w-full min-w-0 sm:min-w-[200px] sm:w-auto text-center cursor-pointer min-h-[120px] flex items-center justify-center
        focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 touch-manipulation
        ${isDragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400'}
        ${isUploading ? 'opacity-60 pointer-events-none' : ''}
      `}
      role="button"
      tabIndex={0}
      aria-label={`Subir documento: ${formatTipo(tipoDocumento)}. PDF, JPG o PNG, máximo 10 MB`}
    >
      <input {...getInputProps()} aria-hidden />
      {isUploading ? (
        <div className="flex items-center justify-center gap-2 text-gray-600">
          <Loader2 className="w-5 h-5 animate-spin" />
          Subiendo…
        </div>
      ) : (
        <div className="flex flex-col items-center gap-1 text-sm text-gray-600">
          <Upload className="w-6 h-6" />
          <span>{isDragActive ? 'Suelta aquí' : 'Arrastra o haz clic'}</span>
          <span className="text-xs text-gray-500">PDF, JPG, PNG · máx. 10 MB</span>
        </div>
      )}
    </div>
  );
}
