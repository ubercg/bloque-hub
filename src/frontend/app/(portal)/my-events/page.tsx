'use client';

/**
 * Portal: listado de reservas/eventos del usuario (Mis eventos)
 */

import Link from 'next/link';
import useSWR from 'swr';
import apiClient from '@/lib/http/apiClient';
import { Calendar, ArrowRight } from 'lucide-react';
import { SkeletonListRow } from '@/components/ui/Skeleton';
import { formatDateOnlyShort } from '@/lib/dateUtils';

interface Reservation {
  id: string;
  tenant_id: string;
  user_id: string;
  space_id: string;
  group_event_id?: string | null;
  event_name?: string | null;
  fecha: string;
  hora_inicio: string;
  hora_fin: string;
  status: string;
  ttl_expires_at: string | null;
  ttl_frozen: boolean;
  created_at: string;
  updated_at: string;
}

interface Space {
  id: string;
  name: string;
  slug: string;
  piso?: number;
  capacidad_maxima: number;
  precio_por_hora: number;
}

const fetcher = (url: string) => apiClient.get(url).then((res) => res.data);

const STATUS_LABELS: Record<string, string> = {
  PENDING_SLIP: 'Pendiente de pase de caja',
  AWAITING_PAYMENT: 'Esperando pago',
  PAYMENT_UNDER_REVIEW: 'Comprobante en revisión',
  CONFIRMED: 'Confirmada',
  COMPLETED: 'Completada',
  EXPIRED: 'Expirada',
  CANCELLED: 'Cancelada',
};

function formatDate(fecha: string, horaInicio: string, horaFin: string) {
  const dateStr = formatDateOnlyShort(fecha, { weekday: 'short', month: 'short' });
  return `${dateStr} · ${horaInicio.slice(0, 5)} – ${horaFin.slice(0, 5)}`;
}

function shortId(id: string) {
  return id.slice(0, 8).toUpperCase();
}

interface EventGroup {
  key: string;
  reservations: Reservation[];
  firstReservationId: string;
  eventName: string;
  dateLabel: string;
  status: string;
  spacesLabel: string;
  uniqueSpaces: number;
  totalHours: number;
}

function toStartTs(r: Reservation): number {
  return new Date(`${r.fecha}T${r.hora_inicio}`).getTime();
}

function totalReservationHours(reservations: Reservation[]): number {
  let total = 0;
  for (const r of reservations) {
    const a = r.hora_inicio.slice(0, 5);
    const b = r.hora_fin.slice(0, 5);
    const [h1, m1] = a.split(':').map(Number);
    const [h2, m2] = b.split(':').map(Number);
    total += (h2 * 60 + m2 - (h1 * 60 + m1)) / 60;
  }
  return Math.round(total * 10) / 10;
}

function uniqueSpaceCount(reservations: Reservation[]): number {
  return new Set(reservations.map((r) => r.space_id)).size;
}

function uniqueSpaceNames(reservations: Reservation[], spaceMap: Map<string, Space>): string[] {
  const names = new Set<string>();
  for (const r of reservations) {
    const space = spaceMap.get(r.space_id);
    names.add(space?.name ?? `Espacio ${shortId(r.space_id)}`);
  }
  return [...names].sort((a, b) => a.localeCompare(b, 'es'));
}

function buildEventGroups(reservations: Reservation[], spaceMap: Map<string, Space>): EventGroup[] {
  const grouped = new Map<string, Reservation[]>();
  for (const r of reservations) {
    const key = r.group_event_id || r.id;
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key)!.push(r);
  }

  return Array.from(grouped.entries())
    .map(([key, group]) => {
      const sorted = [...group].sort((a, b) => toStartTs(a) - toStartTs(b));
      const first = sorted[0];
      const last = sorted[sorted.length - 1];
      const dateLabel =
        sorted.length > 1
          ? `${formatDateOnlyShort(first.fecha, { weekday: 'short', month: 'short' })} – ${formatDateOnlyShort(last.fecha, {
              weekday: 'short',
              month: 'short',
            })}`
          : formatDate(first.fecha, first.hora_inicio, first.hora_fin);
      const spaces = uniqueSpaceNames(sorted, spaceMap);
      const spacesLabel =
        spaces.length <= 2 ? spaces.join(' · ') : `${spaces.slice(0, 2).join(' · ')} +${spaces.length - 2} espacios`;
      return {
        key,
        reservations: sorted,
        firstReservationId: first.id,
        eventName: first.event_name || `Evento ${shortId(key)}`,
        dateLabel,
        status: first.status,
        spacesLabel,
        uniqueSpaces: uniqueSpaceCount(sorted),
        totalHours: totalReservationHours(sorted),
      };
    })
    .sort((a, b) => toStartTs(b.reservations[0]) - toStartTs(a.reservations[0]));
}

export default function MyEventsPage() {
  const { data: reservations, error, isLoading } = useSWR<Reservation[]>(
    '/reservations',
    fetcher,
    { revalidateOnFocus: true, dedupingInterval: 30000 }
  );
  const { data: spaces } = useSWR<Space[]>('/spaces', fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 60000,
  });

  const spaceMap = new Map<string, Space>();
  spaces?.forEach((s) => spaceMap.set(s.id, s));

  if (isLoading) {
    return (
      <div>
        <div className="h-9 w-64 rounded-md bg-gray-200 animate-pulse mb-2" />
        <div className="h-5 w-96 rounded-md bg-gray-200 animate-pulse mb-8" />
        <ul className="space-y-0 border border-gray-200 rounded-xl divide-y divide-gray-100 bg-white overflow-hidden">
          {[1, 2, 3, 4, 5].map((i) => (
            <li key={i}>
              <SkeletonListRow />
            </li>
          ))}
        </ul>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
        <p className="text-red-700">
          No se pudieron cargar tus reservas. Verifica tu sesión e intenta de nuevo.
        </p>
        <Link
          href="/login"
          className="mt-4 inline-block px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
        >
          Iniciar sesión
        </Link>
      </div>
    );
  }

  const list = reservations ?? [];
  const eventGroups = buildEventGroups(list, spaceMap);

  return (
    <div>
      <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 mb-2">Mis eventos</h1>
      <p className="text-gray-600 mb-6 sm:mb-8 text-sm sm:text-base">
        Aquí puedes ver el estado de tus reservas y comunicarte con operaciones.
      </p>

      {eventGroups.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-8 sm:p-12 text-center">
          <Calendar className="w-14 h-14 sm:w-16 sm:h-16 text-gray-300 mx-auto mb-4" aria-hidden />
          <p className="text-gray-600 mb-4">No tienes reservas aún.</p>
          <Link
            href="/catalog"
            className="inline-flex items-center justify-center gap-2 px-5 py-3 min-h-[44px] bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium touch-manipulation"
          >
            Explorar catálogo
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      ) : (
        <ul className="space-y-3 sm:space-y-4">
          {eventGroups.map((event) => {
            const totalSlots = event.reservations.length;
            return (
              <li key={event.key}>
                <Link
                  href={`/my-events/${event.firstReservationId}`}
                  className="block bg-white rounded-xl border border-gray-200 p-4 sm:p-5 hover:border-blue-300 hover:shadow-md transition-all min-h-[72px] touch-manipulation"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="font-mono text-xs sm:text-sm text-gray-500 mb-0.5">
                        Evento {shortId(event.key)}
                      </div>
                      <div className="font-semibold text-gray-900 truncate">{event.eventName}</div>
                      <div className="text-xs sm:text-sm text-gray-600 mt-0.5">
                        {event.dateLabel}
                      </div>
                      <div className="text-xs sm:text-sm text-gray-500 mt-0.5 truncate">
                        {event.spacesLabel} · {event.uniqueSpaces} espacio(s) · {event.totalHours} h · {totalSlots}{' '}
                        slot(s)
                      </div>
                      <span
                        className={`inline-block mt-2 px-2 py-0.5 rounded text-xs font-medium ${
                          event.status === 'CONFIRMED'
                            ? 'bg-green-100 text-green-800'
                            : event.status === 'COMPLETED'
                              ? 'bg-blue-100 text-blue-800'
                              : event.status === 'EXPIRED' || event.status === 'CANCELLED'
                                ? 'bg-gray-100 text-gray-600'
                                : 'bg-amber-100 text-amber-800'
                        }`}
                      >
                        {STATUS_LABELS[event.status] ?? event.status}
                      </span>
                    </div>
                    <ArrowRight className="w-5 h-5 text-gray-400 flex-shrink-0" aria-hidden />
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
