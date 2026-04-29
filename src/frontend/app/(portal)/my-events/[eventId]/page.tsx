'use client';

/**
 * Portal: detalle de un evento (reserva) con línea de tiempo y mensajes
 */

import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import useSWR from 'swr';
import apiClient from '@/lib/http/apiClient';
import {
  Loader2,
  ArrowLeft,
  FileText,
  MessageCircle,
  FolderOpen,
  QrCode,
  CheckCircle,
  Circle,
  XCircle,
  CreditCard,
  Clock,
  AlertTriangle,
  Shield,
  Upload,
  Download,
  Eye,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';
import { EvidenceUploader } from '@/features/evidence';
import {
  EventSpaceSummary,
  type EventSummarySpace,
} from '@/features/portal/EventSpaceSummary';
import { parseDateOnlyAsLocal } from '@/lib/dateUtils';

interface Reservation {
  id: string;
  space_id: string;
  group_event_id?: string | null;
  event_name?: string | null;
  fecha: string;
  hora_inicio: string;
  hora_fin: string;
  status: string;
  created_at: string;
  updated_at: string;
  ttl_expires_at?: string | null;
  ttl_frozen?: boolean;
}

interface Voucher {
  id: string;
  reservation_id: string;
  file_url: string;
  file_type: string;
  file_size_kb?: number;
  uploaded_at: string;
}

interface Space {
  id: string;
  name: string;
  slug: string;
}

interface PortalMessage {
  id: string;
  reservation_id: string;
  remitente_tipo: string;
  mensaje: string;
  enviado_at: string;
  leido_at: string | null;
}

const fetcher = (url: string) => apiClient.get(url).then((res) => res.data);

const TIMELINE_STEPS = [
  { key: 'PENDING_SLIP', label: 'Pre-reserva creada', next: 'Solicita tu Pase de Caja' },
  { key: 'AWAITING_PAYMENT', label: 'Esperando pago', next: 'Realiza el pago SPEI y sube comprobante' },
  { key: 'PAYMENT_UNDER_REVIEW', label: 'Comprobante en revisión', next: 'Finanzas validará tu pago' },
  { key: 'CONFIRMED', label: 'Reserva confirmada', next: 'Sube documentos y prepara tu evento' },
  { key: 'COMPLETED', label: 'Evento completado', next: '' },
  { key: 'EXPIRED', label: 'Expirada', next: '' },
  { key: 'CANCELLED', label: 'Cancelada', next: '' },
];

const STATUS_LABELS: Record<string, string> = {
  PENDING_SLIP: 'Pendiente de pase de caja',
  AWAITING_PAYMENT: 'Esperando pago',
  PAYMENT_UNDER_REVIEW: 'Comprobante en revisión',
  CONFIRMED: 'Confirmada',
  COMPLETED: 'Completada',
  EXPIRED: 'Expirada',
  CANCELLED: 'Cancelada',
};

interface EventSummaryResponse {
  event: {
    group_event_id: string | null;
    name: string | null;
    date_from: string;
    date_to: string;
    status_primary: string;
    status_is_mixed: boolean;
  };
  totals: { unique_spaces: number; total_hours: number };
  spaces: EventSummarySpace[];
}

function TtlCountdown({ expiresAt }: { expiresAt: string }) {
  const [remaining, setRemaining] = useState('');
  const [isUrgent, setIsUrgent] = useState(false);

  useEffect(() => {
    const update = () => {
      const now = Date.now();
      const exp = new Date(expiresAt).getTime();
      const diff = exp - now;
      if (diff <= 0) {
        setRemaining('Expirado');
        setIsUrgent(true);
        return;
      }
      const hours = Math.floor(diff / (1000 * 60 * 60));
      const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
      setRemaining(`${hours}h ${minutes}m`);
      setIsUrgent(diff < 2 * 60 * 60 * 1000); // < 2 hours
    };
    update();
    const interval = setInterval(update, 60000);
    return () => clearInterval(interval);
  }, [expiresAt]);

  return (
    <section className={`rounded-xl border p-4 sm:p-6 ${
      isUrgent ? 'bg-red-50 border-red-200' : 'bg-gray-50 border-gray-200'
    }`}>
      <div className="flex items-center gap-3">
        {isUrgent ? (
          <AlertTriangle className="w-6 h-6 text-red-600 flex-shrink-0" />
        ) : (
          <Clock className="w-6 h-6 text-gray-600 flex-shrink-0" />
        )}
        <p className={`text-sm font-medium ${isUrgent ? 'text-red-800' : 'text-gray-700'}`}>
          Tiempo restante: {remaining}
        </p>
      </div>
    </section>
  );
}

function isValidUUID(str: string): boolean {
  const u =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  return u.test(str);
}

export default function EventDetailPage() {
  const params = useParams();
  const eventId = (params?.eventId as string) ?? '';
  const [messageText, setMessageText] = useState('');
  const [sending, setSending] = useState(false);
  const [messageError, setMessageError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [deletingVoucherId, setDeletingVoucherId] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);

  const validId = eventId && isValidUUID(eventId);

  const { data: reservation, error: resError, mutate: mutateReservation } = useSWR<Reservation>(
    validId ? `/reservations/${eventId}` : null,
    fetcher,
    { revalidateOnFocus: true }
  );
  const { data: allReservations } = useSWR<Reservation[]>(
    validId ? '/reservations' : null,
    fetcher,
    { revalidateOnFocus: true, dedupingInterval: 30000 }
  );
  const { data: spaces } = useSWR<Space[]>(
    '/spaces',
    fetcher,
    { revalidateOnFocus: false }
  );
  const { data: messages, mutate: mutateMessages } = useSWR<PortalMessage[]>(
    validId ? `/reservations/${eventId}/messages` : null,
    fetcher,
    { revalidateOnFocus: true }
  );
  const {
    data: eventSummary,
    error: eventSummaryError,
    isLoading: eventSummaryLoading,
  } = useSWR<EventSummaryResponse>(
    validId ? `/reservations/${eventId}/event-summary` : null,
    fetcher,
    { revalidateOnFocus: true }
  );
  const showVouchers =
    reservation &&
    ['AWAITING_PAYMENT', 'PAYMENT_UNDER_REVIEW', 'CONFIRMED', 'COMPLETED'].includes(reservation.status);
  const { data: vouchers = [], mutate: mutateVouchers } = useSWR<Voucher[]>(
    validId && showVouchers ? `/reservations/${eventId}/vouchers` : null,
    fetcher
  );
  const canManageVouchers =
    reservation &&
    (reservation.status === 'AWAITING_PAYMENT' || reservation.status === 'PAYMENT_UNDER_REVIEW');

  const sendMessage = useCallback(async () => {
    const text = messageText.trim();
    if (!text || !validId || sending) return;
    setSending(true);
    setMessageError(null);
    try {
      await apiClient.post(`/reservations/${eventId}/messages`, { mensaje: text });
      setMessageText('');
      await mutateMessages();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setMessageError(err.response?.data?.detail ?? 'Error al enviar. Intenta de nuevo.');
    } finally {
      setSending(false);
    }
  }, [eventId, messageText, validId, sending, mutateMessages]);

  const canCancel =
    reservation &&
    (reservation.status === 'PENDING_SLIP' || reservation.status === 'AWAITING_PAYMENT');

  const handleCancel = useCallback(async () => {
    if (!validId || !canCancel || cancelling) return;
    if (!confirm('¿Cancelar esta solicitud? Se liberará el horario reservado.')) return;
    setCancelling(true);
    try {
      await apiClient.post(`/reservations/${eventId}/cancel`);
      toast.success('Solicitud cancelada.');
      await mutateReservation();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      toast.error(err.response?.data?.detail ?? 'No se pudo cancelar.');
    } finally {
      setCancelling(false);
    }
  }, [eventId, validId, canCancel, cancelling, mutateReservation]);

  const handleDownloadVoucher = useCallback(async (v: Voucher) => {
    const url = `/reservations/${v.reservation_id}/vouchers/${v.id}/download`;
    try {
      const res = await apiClient.get(url, { responseType: 'blob' });
      const blob = new Blob([res.data], { type: v.file_type });
      const objectUrl = URL.createObjectURL(blob);
      if (v.file_type?.startsWith('image/')) {
        window.open(objectUrl, '_blank');
      } else {
        const a = document.createElement('a');
        a.href = objectUrl;
        a.download = v.file_url || 'comprobante';
        a.click();
        URL.revokeObjectURL(objectUrl);
      }
    } catch (e: unknown) {
      const ax = e as { response?: { status?: number; data?: Blob } };
      let msg = 'No se pudo descargar el comprobante.';
      if (ax.response?.data instanceof Blob && ax.response.data.type?.includes('application/json')) {
        try {
          const text = await ax.response.data.text();
          const obj = JSON.parse(text) as { detail?: string };
          msg = obj.detail ?? msg;
        } catch {
          msg = 'Comprobante o archivo no encontrado.';
        }
      }
      toast.error(msg);
    }
  }, []);

  const handleDeleteVoucher = useCallback(async (v: Voucher) => {
    if (!confirm('¿Eliminar este comprobante? Podrás subir otro si lo necesitas.')) return;
    setDeletingVoucherId(v.id);
    try {
      await apiClient.delete(`/reservations/${v.reservation_id}/vouchers/${v.id}`);
      toast.success('Comprobante eliminado.');
      await mutateVouchers();
      await mutateReservation();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      toast.error(err.response?.data?.detail ?? 'No se pudo eliminar.');
    } finally {
      setDeletingVoucherId(null);
    }
  }, [mutateVouchers, mutateReservation]);

  const handleDownloadPrecotizacion = useCallback(async () => {
    if (!validId) return;
    setPdfLoading(true);
    try {
      const res = await apiClient.get(`/reservations/${eventId}/event-precotizacion.pdf`, {
        responseType: 'blob',
      });
      const blob = new Blob([res.data], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `precotizacion-${eventId}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success('Descarga iniciada.');
    } catch {
      toast.error('No se pudo descargar la precotización.');
    } finally {
      setPdfLoading(false);
    }
  }, [eventId, validId]);

  if (!validId) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-600 mb-4">Evento no válido.</p>
        <Link href="/my-events" className="text-blue-600 hover:underline">
          Volver a Mis eventos
        </Link>
      </div>
    );
  }

  if (resError) {
    const status = (resError as { response?: { status?: number } })?.response?.status;
    return (
      <div className="text-center py-12">
        <p className="text-gray-600 mb-4">
          {status === 403 || status === 404
            ? 'No tienes acceso a este evento o no existe.'
            : 'Error al cargar el evento.'}
        </p>
        <Link
          href="/my-events"
          className="inline-flex items-center gap-2 text-blue-600 hover:underline"
        >
          <ArrowLeft className="w-4 h-4" />
          Volver a Mis eventos
        </Link>
      </div>
    );
  }

  if (!reservation) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
        <span className="ml-3 text-gray-600">Cargando...</span>
      </div>
    );
  }

  const eventGroupKey = reservation.group_event_id ?? reservation.id;
  const eventReservationsRaw = (allReservations ?? [reservation]).filter(
    (r) => (r.group_event_id ?? r.id) === eventGroupKey
  );
  const eventReservations = (eventReservationsRaw.length > 0 ? eventReservationsRaw : [reservation]).sort((a, b) => {
    const ta = new Date(`${a.fecha}T${a.hora_inicio}`).getTime();
    const tb = new Date(`${b.fecha}T${b.hora_inicio}`).getTime();
    return ta - tb;
  });

  const spaceMap = new Map<string, Space>();
  (spaces ?? []).forEach((s) => spaceMap.set(s.id, s));
  const reservationSpaceName = (r: Reservation) => spaceMap.get(r.space_id)?.name ?? `Espacio ${r.space_id.slice(0, 8).toUpperCase()}`;
  const eventName = reservation.event_name ?? `Evento ${eventGroupKey.slice(0, 8).toUpperCase()}`;
  const firstReservation = eventReservations[0];
  const lastReservation = eventReservations[eventReservations.length - 1];
  const eventDateLabel =
    firstReservation && lastReservation
      ? `${parseDateOnlyAsLocal(firstReservation.fecha).toLocaleDateString('es-MX', {
          timeZone: 'America/Mexico_City',
          weekday: 'long',
          year: 'numeric',
          month: 'long',
          day: 'numeric',
        })} — ${parseDateOnlyAsLocal(lastReservation.fecha).toLocaleDateString('es-MX', {
          timeZone: 'America/Mexico_City',
          weekday: 'long',
          year: 'numeric',
          month: 'long',
          day: 'numeric',
        })}`
      : '—';

  const currentStepIndex = TIMELINE_STEPS.findIndex((s) => s.key === reservation.status);
  const messageList = messages ?? [];

  return (
    <div className="space-y-6 sm:space-y-8">
      <div>
        <Link
          href="/my-events"
          className="inline-flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-4 min-h-[44px] touch-manipulation"
        >
          <ArrowLeft className="w-4 h-4" />
          Mis eventos
        </Link>
        <h1 className="text-xl sm:text-2xl font-bold text-gray-900">{eventName}</h1>
        <p className="text-gray-600 text-sm sm:text-base">
          {eventSummary
            ? `${eventSummary.totals.unique_spaces} espacio(s) · ${eventSummary.totals.total_hours} h totales · ${eventReservations.length} slot(s)`
            : `${eventDateLabel} · ${eventReservations.length} horarios`}
        </p>
        {eventSummary && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span
              className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                eventSummary.event.status_is_mixed
                  ? 'bg-violet-100 text-violet-800'
                  : eventSummary.event.status_primary === 'CONFIRMED'
                    ? 'bg-green-100 text-green-800'
                    : eventSummary.event.status_primary === 'EXPIRED' ||
                        eventSummary.event.status_primary === 'CANCELLED'
                      ? 'bg-gray-100 text-gray-600'
                      : eventSummary.event.status_primary === 'PAYMENT_UNDER_REVIEW'
                        ? 'bg-purple-100 text-purple-800'
                        : eventSummary.event.status_primary === 'AWAITING_PAYMENT'
                          ? 'bg-blue-100 text-blue-800'
                          : 'bg-amber-100 text-amber-800'
              }`}
            >
              {eventSummary.event.status_is_mixed
                ? 'Varios estados entre slots'
                : STATUS_LABELS[eventSummary.event.status_primary] ?? eventSummary.event.status_primary}
            </span>
          </div>
        )}
      </div>

      <section className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-4">
          <h2 className="font-semibold text-gray-900">Resumen del evento</h2>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={handleDownloadPrecotizacion}
              disabled={pdfLoading}
              className="inline-flex items-center justify-center gap-2 px-4 py-2.5 min-h-[44px] rounded-lg border border-gray-300 bg-white text-gray-800 hover:bg-gray-50 text-sm font-medium disabled:opacity-50 touch-manipulation"
            >
              <Download className="w-4 h-4 flex-shrink-0" />
              {pdfLoading ? 'Generando…' : 'Descargar precotización (PDF)'}
            </button>
            <a
              href="#contacto-operaciones"
              className="inline-flex items-center justify-center gap-2 px-4 py-2.5 min-h-[44px] rounded-lg border border-blue-200 bg-blue-50 text-blue-800 hover:bg-blue-100 text-sm font-medium touch-manipulation"
            >
              <MessageCircle className="w-4 h-4 flex-shrink-0" />
              Contactar operaciones
            </a>
          </div>
        </div>
        {eventSummaryLoading && (
          <div className="animate-pulse h-40 bg-gray-100 rounded-lg" aria-hidden />
        )}
        {!eventSummaryLoading && eventSummary && (
          <EventSpaceSummary
            spaces={eventSummary.spaces}
            flatReservations={eventReservations.map((r) => ({
              id: r.id,
              fecha: r.fecha,
              hora_inicio: r.hora_inicio,
              hora_fin: r.hora_fin,
              status: r.status,
            }))}
          />
        )}
        {!eventSummaryLoading && eventSummaryError && (
          <div className="space-y-3">
            <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
              No se pudo cargar el resumen agrupado. Mostramos cada slot por separado.
            </p>
            <div className="space-y-2">
              {eventReservations.map((r) => {
                const statusLabel = STATUS_LABELS[r.status] ?? r.status;
                return (
                  <div
                    key={r.id}
                    className="flex items-start justify-between gap-3 p-3 rounded-lg border border-gray-100 bg-gray-50"
                  >
                    <div className="min-w-0">
                      <div className="font-medium text-gray-900">{reservationSpaceName(r)}</div>
                      <div className="text-sm text-gray-600">
                        {parseDateOnlyAsLocal(r.fecha).toLocaleDateString('es-MX', {
                          timeZone: 'America/Mexico_City',
                          day: '2-digit',
                          month: 'long',
                          year: 'numeric',
                        })}{' '}
                        · {r.hora_inicio.slice(0, 5)} – {r.hora_fin.slice(0, 5)}
                      </div>
                      <div className="text-xs text-gray-500 font-mono mt-1">
                        Folio {r.id.slice(0, 8).toUpperCase()}
                      </div>
                    </div>
                    <span
                      className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                        r.status === 'CONFIRMED'
                          ? 'bg-green-100 text-green-800'
                          : r.status === 'COMPLETED'
                            ? 'bg-blue-100 text-blue-800'
                            : r.status === 'EXPIRED' || r.status === 'CANCELLED'
                              ? 'bg-gray-100 text-gray-600'
                              : 'bg-amber-100 text-amber-800'
                      }`}
                    >
                      {statusLabel}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </section>

      {/* Línea de tiempo */}
      <section className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <FileText className="w-5 h-5" />
          Estado de tu reserva
        </h2>
        <div className="relative">
          {TIMELINE_STEPS.filter((s) => s.key !== 'EXPIRED' && s.key !== 'CANCELLED' && s.key !== 'COMPLETED').map((step, i) => {
            const isActive = step.key === reservation.status;
            const isPast =
              currentStepIndex >= 0 && i < currentStepIndex;
            const isExpired = reservation.status === 'EXPIRED';
            const isCancelled = reservation.status === 'CANCELLED';
            return (
              <div key={step.key} className="flex gap-4 pb-6 last:pb-0">
                <div className="flex flex-col items-center">
                  {isPast ? (
                    <CheckCircle className="w-6 h-6 text-green-600" />
                  ) : isActive && !isExpired && !isCancelled ? (
                    <div className="w-6 h-6 rounded-full border-2 border-blue-600 bg-blue-50" />
                  ) : (
                    <Circle className="w-6 h-6 text-gray-300" />
                  )}
                  {i < TIMELINE_STEPS.length - 2 && (
                    <div
                      className={`w-0.5 flex-1 min-h-[24px] ${
                        isPast ? 'bg-green-200' : 'bg-gray-200'
                      }`}
                    />
                  )}
                </div>
                <div className="flex-1">
                  <div
                    className={
                      isActive && !isExpired
                        ? 'font-medium text-gray-900'
                        : isPast
                          ? 'text-gray-700'
                          : 'text-gray-400'
                    }
                  >
                    {step.label}
                  </div>
                  {isActive && step.next && reservation.status !== 'EXPIRED' && reservation.status !== 'CANCELLED' && (
                    <div className="text-sm text-amber-700 mt-1">{step.next}</div>
                  )}
                </div>
              </div>
            );
          })}
          {reservation.status === 'EXPIRED' && (
            <div className="flex gap-4">
              <Circle className="w-6 h-6 text-gray-400 flex-shrink-0" />
              <div className="text-gray-500">Esta reserva expiró.</div>
            </div>
          )}
          {reservation.status === 'CANCELLED' && (
            <div className="flex gap-4">
              <XCircle className="w-6 h-6 text-amber-600 flex-shrink-0" />
              <div className="text-gray-500">Esta solicitud fue cancelada.</div>
            </div>
          )}
          {reservation.status === 'COMPLETED' && (
            <div className="flex gap-4">
              <CheckCircle className="w-6 h-6 text-green-600 flex-shrink-0" />
              <div>
                <div className="text-gray-700 font-medium">Evento completado</div>
                <p className="text-sm text-gray-600 mt-1">Tu evento ha finalizado. Gracias por elegir BLOQUE.</p>
              </div>
            </div>
          )}
        </div>
        {canCancel && (
          <div className="mt-4 pt-4 border-t border-gray-200">
            <button
              type="button"
              onClick={handleCancel}
              disabled={cancelling}
              className="inline-flex items-center gap-2 px-4 py-2 min-h-[44px] rounded-lg border border-red-300 text-red-700 bg-red-50 hover:bg-red-100 font-medium disabled:opacity-50 touch-manipulation"
              aria-label="Cancelar esta solicitud"
            >
              <XCircle className="w-5 h-5" />
              {cancelling ? 'Cancelando…' : 'Cancelar solicitud'}
            </button>
          </div>
        )}
      </section>

      {/* Info contextual por status */}
      {reservation.status === 'PENDING_SLIP' && (
        <section className="bg-amber-50 rounded-xl border border-amber-200 p-4 sm:p-6">
          <div className="flex items-start gap-3">
            <Clock className="w-6 h-6 text-amber-600 flex-shrink-0 mt-0.5" />
            <div>
              <h3 className="font-semibold text-gray-900 mb-1">Generando tu Pase de Caja</h3>
              <p className="text-sm text-gray-700">
                Estamos generando tu Pase de Caja. Recibiras un correo con los datos de pago en menos de 4 horas habiles.
              </p>
            </div>
          </div>
        </section>
      )}

      {reservation.status === 'AWAITING_PAYMENT' && (
        <section className="bg-blue-50 rounded-xl border border-blue-200 p-4 sm:p-6">
          <div className="flex items-start gap-3">
            <CreditCard className="w-6 h-6 text-blue-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <h3 className="font-semibold text-gray-900 mb-1">Datos de pago</h3>
              <p className="text-sm text-gray-700 mb-3">
                Revisa tu correo para obtener la CLABE y referencia SPEI. Realiza la transferencia antes de que expire el plazo.
              </p>
              <Link
                href={`/booking/upload-voucher?id=${eventId}`}
                className="inline-flex items-center gap-2 px-4 py-2.5 min-h-[44px] bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium touch-manipulation"
              >
                <Upload className="w-5 h-5" />
                Subir comprobante de pago
              </Link>
            </div>
          </div>
        </section>
      )}

      {reservation.status === 'PAYMENT_UNDER_REVIEW' && (
        <section className="bg-purple-50 rounded-xl border border-purple-200 p-4 sm:p-6">
          <div className="flex items-start gap-3">
            <FileText className="w-6 h-6 text-purple-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <h3 className="font-semibold text-gray-900 mb-1">Comprobante en revisión</h3>
              <p className="text-sm text-gray-700 mb-3">
                Tu comprobante está en revisión. Si Finanzas no puede verlo o necesitas reemplazarlo, puedes eliminarlo y subir otro.
              </p>
              <Link
                href={`/booking/upload-voucher?id=${eventId}`}
                className="inline-flex items-center gap-2 px-4 py-2.5 min-h-[44px] bg-purple-600 text-white rounded-lg hover:bg-purple-700 font-medium touch-manipulation"
              >
                <Upload className="w-5 h-5" />
                Subir otro comprobante
              </Link>
            </div>
          </div>
        </section>
      )}

      {reservation.status === 'COMPLETED' && (
        <section className="bg-green-50 rounded-xl border border-green-200 p-4 sm:p-6">
          <div className="flex items-start gap-3">
            <CheckCircle className="w-6 h-6 text-green-600 flex-shrink-0 mt-0.5" />
            <div>
              <h3 className="font-semibold text-gray-900 mb-1">Evento completado</h3>
              <p className="text-sm text-gray-700">
                Tu evento ha finalizado. Gracias por elegir BLOQUE.
              </p>
            </div>
          </div>
        </section>
      )}

      {/* TTL Countdown */}
      {reservation.ttl_expires_at &&
        !reservation.ttl_frozen &&
        (reservation.status === 'PENDING_SLIP' || reservation.status === 'AWAITING_PAYMENT') && (
          <TtlCountdown expiresAt={reservation.ttl_expires_at} />
        )}
      {reservation.ttl_frozen && (
        <section className="bg-green-50 rounded-xl border border-green-200 p-4 sm:p-6">
          <div className="flex items-center gap-3">
            <Shield className="w-6 h-6 text-green-600 flex-shrink-0" />
            <p className="text-sm font-medium text-green-800">
              Comprobante recibido — tu reserva esta protegida
            </p>
          </div>
        </section>
      )}

      {/* Comprobantes de pago: ver, descargar, eliminar, subir otro */}
      {showVouchers && (
        <section className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
          <h2 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <FileText className="w-5 h-5" />
            Comprobantes de pago
          </h2>
          {vouchers.length === 0 ? (
            <p className="text-sm text-gray-500 mb-3">Aún no has subido comprobantes.</p>
          ) : (
            <div className="space-y-2 mb-4">
              {vouchers.map((v) => (
                <div
                  key={v.id}
                  className="flex flex-wrap items-center justify-between gap-2 p-3 bg-gray-50 rounded-lg text-sm"
                >
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-gray-900 truncate">{v.file_url}</div>
                    <div className="text-xs text-gray-500">
                      {new Date(v.uploaded_at).toLocaleString('es-MX', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Mexico_City' })}
                      {v.file_size_kb != null && ` · ${v.file_size_kb} KB`}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <button
                      type="button"
                      onClick={() => handleDownloadVoucher(v)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 min-h-[44px] rounded-lg bg-blue-100 text-blue-800 hover:bg-blue-200 font-medium touch-manipulation"
                      aria-label={v.file_type?.startsWith('image/') ? 'Ver imagen' : 'Descargar comprobante'}
                    >
                      {v.file_type?.startsWith('image/') ? (
                        <Eye className="w-4 h-4" />
                      ) : (
                        <Download className="w-4 h-4" />
                      )}
                      {v.file_type?.startsWith('image/') ? 'Ver' : 'Descargar'}
                    </button>
                    {canManageVouchers && (
                      <button
                        type="button"
                        onClick={() => handleDeleteVoucher(v)}
                        disabled={deletingVoucherId === v.id}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 min-h-[44px] rounded-lg bg-red-100 text-red-800 hover:bg-red-200 font-medium touch-manipulation disabled:opacity-50"
                        aria-label="Eliminar comprobante"
                      >
                        {deletingVoucherId === v.id ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <Trash2 className="w-4 h-4" />
                        )}
                        Eliminar
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
          {canManageVouchers && (
            <Link
              href={`/booking/upload-voucher?id=${eventId}`}
              className="inline-flex items-center gap-2 px-4 py-2.5 min-h-[44px] bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium touch-manipulation"
            >
              <Upload className="w-5 h-5" />
              {vouchers.length > 0 ? 'Subir otro comprobante' : 'Subir comprobante de pago'}
            </Link>
          )}
        </section>
      )}

      {/* Mensajes */}
      <section
        id="contacto-operaciones"
        className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6 scroll-mt-24"
      >
        <h2 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <MessageCircle className="w-5 h-5 flex-shrink-0" />
          Mensajes con Operaciones
        </h2>
        <div className="space-y-3 max-h-48 sm:max-h-60 overflow-y-auto mb-4">
          {messageList.length === 0 ? (
            <p className="text-gray-500 text-sm">Aún no hay mensajes.</p>
          ) : (
            messageList.map((m) => (
              <div
                key={m.id}
                className={`p-3 rounded-lg text-sm ${
                  m.remitente_tipo === 'CUSTOMER'
                    ? 'bg-blue-50 ml-2 sm:ml-4'
                    : 'bg-gray-100 mr-2 sm:mr-4'
                }`}
              >
                <div className="text-xs text-gray-500 mb-1">
                  {m.remitente_tipo === 'CUSTOMER' ? 'Tú' : 'Operaciones'} ·{' '}
                  {new Date(m.enviado_at).toLocaleString('es-MX')}
                </div>
                <div className="text-gray-900 break-words">{m.mensaje}</div>
              </div>
            ))
          )}
        </div>
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            type="text"
            value={messageText}
            onChange={(e) => setMessageText(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
            placeholder="Escribe un mensaje..."
            className="flex-1 min-h-[44px] px-3 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-base"
            aria-label="Mensaje para operaciones"
          />
          <button
            type="button"
            onClick={sendMessage}
            disabled={!messageText.trim() || sending}
            className="min-h-[44px] px-4 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed touch-manipulation font-medium"
          >
            {sending ? 'Enviando…' : 'Enviar'}
          </button>
        </div>
        {messageError && (
          <p className="mt-2 text-sm text-red-600" role="alert">
            {messageError}
          </p>
        )}
      </section>

      {/* Enlaces a evidencias y acceso */}
      <div className="flex flex-wrap gap-3">
        <Link
          href={`/my-events/${eventId}/access`}
          className="inline-flex items-center justify-center gap-2 px-4 py-3 min-h-[44px] bg-gray-100 text-gray-800 rounded-lg hover:bg-gray-200 font-medium touch-manipulation"
        >
          <QrCode className="w-5 h-5 flex-shrink-0" />
          Acceso y factura
        </Link>
      </div>

      {/* Buzón de Evidencias */}
      <section className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
        <h2 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <FolderOpen className="w-5 h-5" />
          Documentos requeridos
        </h2>
        <EvidenceUploader reservationId={eventId} />
      </section>
    </div>
  );
}
