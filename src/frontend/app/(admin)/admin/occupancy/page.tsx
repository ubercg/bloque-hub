'use client';

import { useMemo, useState } from 'react';
import useSWR from 'swr';
import { CalendarDays, Filter, Building2, Clock3, UserRound, X, ExternalLink, Copy } from 'lucide-react';

import { CAN_ACCESS_STAFF_MONITOR, RoleGuard } from '@/features/auth';
import apiClient from '@/lib/http/apiClient';
import { formatDateOnlyLocal, todayMexico } from '@/lib/dateUtils';

type OccupancyStatus = 'AVAILABLE' | 'TENTATIVE' | 'CONFIRMED';

interface OccupancySlot {
  slot_id: string;
  fecha: string;
  hora_inicio: string;
  hora_fin: string;
  duracion_horas: number;
  space_id: string;
  space_name: string;
  slot_status: string;
  occupancy_status: OccupancyStatus;
  reservation_id: string | null;
  group_event_id: string | null;
  event_name: string | null;
  reservation_status: string | null;
  customer_name: string | null;
  customer_email: string | null;
  related_space_name: string | null;
  related_event_name: string | null;
  related_customer_name: string | null;
}

const fetcher = (url: string) => apiClient.get(url).then((r) => r.data);
const DAY_START_HOUR = 7;
const DAY_END_HOUR = 22;
const TOTAL_MINUTES = (DAY_END_HOUR - DAY_START_HOUR) * 60;

function plusDays(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + days);
  return d.toLocaleDateString('en-CA', { timeZone: 'America/Mexico_City' });
}

function statusChip(status: OccupancyStatus) {
  if (status === 'CONFIRMED') return 'bg-green-100 text-green-800';
  if (status === 'TENTATIVE') return 'bg-amber-100 text-amber-800';
  return 'bg-gray-100 text-gray-700';
}

function statusLabel(status: OccupancyStatus) {
  if (status === 'CONFIRMED') return 'Confirmado';
  if (status === 'TENTATIVE') return 'Tentativo';
  return 'Disponible';
}

function barColor(status: OccupancyStatus) {
  if (status === 'CONFIRMED') return 'bg-green-500';
  if (status === 'TENTATIVE') return 'bg-amber-500';
  return 'bg-gray-300';
}

/** Misma paleta que /admin/operations (estado de reserva). */
function reservationWorkflowBarClass(status: string | null | undefined): string {
  if (!status) return 'bg-gray-400';
  switch (status) {
    case 'PENDING_SLIP':
      return 'bg-amber-500';
    case 'CONFIRMED':
      return 'bg-emerald-600';
    case 'AWAITING_PAYMENT':
      return 'bg-blue-600';
    case 'PAYMENT_UNDER_REVIEW':
      return 'bg-violet-600';
    case 'EXPIRED':
    case 'CANCELLED':
      return 'bg-gray-400';
    default:
      return 'bg-slate-500';
  }
}

function blockGroupKey(s: OccupancySlot): string {
  if (s.group_event_id) return `g:${s.group_event_id}`;
  if (s.reservation_id) return `r:${s.reservation_id}`;
  if (s.occupancy_status === 'AVAILABLE') return 'AVAILABLE';
  return `slot:${s.slot_id}`;
}

function timesTouch(end: string, start: string): boolean {
  return end.slice(0, 8) === start.slice(0, 8);
}

interface OccupancyMergedBlock {
  hora_inicio: string;
  hora_fin: string;
  slots: OccupancySlot[];
}

/**
 * Fusiona slots consecutivos en la misma franja horaria (mismo evento/reserva o disponible continuo),
 * alineado con la lógica de merge de operaciones.
 */
function mergeSlotsToBlocks(rowSlots: OccupancySlot[]): OccupancyMergedBlock[] {
  const sorted = [...rowSlots].sort((a, b) => timeToMinutes(a.hora_inicio) - timeToMinutes(b.hora_inicio));
  const out: OccupancyMergedBlock[] = [];
  for (const slot of sorted) {
    const prev = out[out.length - 1];
    const sameChain =
      prev &&
      blockGroupKey(prev.slots[0]) === blockGroupKey(slot) &&
      timesTouch(prev.hora_fin, slot.hora_inicio);
    if (sameChain) {
      prev.hora_fin = slot.hora_fin;
      prev.slots.push(slot);
    } else {
      out.push({
        hora_inicio: slot.hora_inicio,
        hora_fin: slot.hora_fin,
        slots: [slot],
      });
    }
  }
  return out;
}

function blockVisualClass(block: OccupancyMergedBlock): string {
  const first = block.slots[0];
  if (first.reservation_status) return reservationWorkflowBarClass(first.reservation_status);
  return barColor(first.occupancy_status);
}

function timeToMinutes(hhmmss: string): number {
  const [h, m] = hhmmss.split(':').map((x) => parseInt(x, 10));
  return (h || 0) * 60 + (m || 0);
}

function leftPct(hhmmss: string): number {
  const min = timeToMinutes(hhmmss);
  const from = DAY_START_HOUR * 60;
  const bounded = Math.max(from, Math.min(min, DAY_END_HOUR * 60));
  return ((bounded - from) / TOTAL_MINUTES) * 100;
}

function widthPct(horaInicio: string, horaFin: string): number {
  const a = Math.max(timeToMinutes(horaInicio), DAY_START_HOUR * 60);
  const b = Math.min(timeToMinutes(horaFin), DAY_END_HOUR * 60);
  const diff = Math.max(0, b - a);
  return (diff / TOTAL_MINUTES) * 100;
}

function OccupancyContent() {
  const today = todayMexico();
  const [fechaDesde, setFechaDesde] = useState(today);
  const [fechaHasta, setFechaHasta] = useState(plusDays(today, 7));
  const [estado, setEstado] = useState<'ALL' | OccupancyStatus>('ALL');
  const [spaceSearch, setSpaceSearch] = useState('');
  const [selectedSlot, setSelectedSlot] = useState<OccupancySlot | null>(null);

  const params = new URLSearchParams();
  params.set('fecha_desde', fechaDesde);
  params.set('fecha_hasta', fechaHasta);
  if (estado !== 'ALL') params.set('estado', estado);

  const { data = [], isLoading, error } = useSWR<OccupancySlot[]>(
    `/admin/occupancy?${params.toString()}`,
    fetcher,
    { revalidateOnFocus: true, dedupingInterval: 15000, refreshInterval: 30000 }
  );

  const filtered = useMemo(() => {
    const q = spaceSearch.trim().toLowerCase();
    if (!q) return data;
    return data.filter((s) => s.space_name.toLowerCase().includes(q));
  }, [data, spaceSearch]);

  const groupedByDay = useMemo(() => {
    const map = new Map<string, OccupancySlot[]>();
    for (const slot of filtered) {
      if (!map.has(slot.fecha)) map.set(slot.fecha, []);
      map.get(slot.fecha)!.push(slot);
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [filtered]);

  const kpis = useMemo(() => {
    return filtered.reduce(
      (acc, s) => {
        if (s.occupancy_status === 'CONFIRMED') acc.confirmed += 1;
        else if (s.occupancy_status === 'TENTATIVE') acc.tentative += 1;
        else acc.available += 1;
        return acc;
      },
      { confirmed: 0, tentative: 0, available: 0 }
    );
  }, [filtered]);

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
        No se pudo cargar el monitor de ocupación. Intenta nuevamente.
      </div>
    );
  }

  return (
    <div className="space-y-6 relative">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Monitor de Ocupación</h1>
        <p className="text-gray-600 text-sm mt-1">
          Vista operativa centralizada de slots por día, espacio, estado y evento.
        </p>
      </div>

      <section className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="rounded-lg border border-green-200 bg-green-50 p-3">
          <p className="text-xs text-green-700">Confirmados</p>
          <p className="text-xl font-bold text-green-800">{kpis.confirmed}</p>
        </div>
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
          <p className="text-xs text-amber-700">Tentativos</p>
          <p className="text-xl font-bold text-amber-800">{kpis.tentative}</p>
        </div>
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
          <p className="text-xs text-gray-600">Disponibles</p>
          <p className="text-xl font-bold text-gray-800">{kpis.available}</p>
        </div>
      </section>

      <section className="bg-white rounded-xl border border-gray-200 p-4">
        <div className="flex items-center gap-2 mb-3">
          <Filter className="w-4 h-4 text-gray-500" />
          <h2 className="font-semibold text-gray-900">Filtros</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <label className="text-sm">
            <span className="text-gray-600">Fecha desde</span>
            <input
              type="date"
              value={fechaDesde}
              onChange={(e) => setFechaDesde(e.target.value)}
              className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2"
            />
          </label>
          <label className="text-sm">
            <span className="text-gray-600">Fecha hasta</span>
            <input
              type="date"
              value={fechaHasta}
              onChange={(e) => setFechaHasta(e.target.value)}
              className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2"
            />
          </label>
          <label className="text-sm">
            <span className="text-gray-600">Estado</span>
            <select
              value={estado}
              onChange={(e) => setEstado(e.target.value as 'ALL' | OccupancyStatus)}
              className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2"
            >
              <option value="ALL">Todos</option>
              <option value="AVAILABLE">Disponible</option>
              <option value="TENTATIVE">Tentativo</option>
              <option value="CONFIRMED">Confirmado</option>
            </select>
          </label>
          <label className="text-sm">
            <span className="text-gray-600">Buscar espacio</span>
            <input
              type="text"
              value={spaceSearch}
              onChange={(e) => setSpaceSearch(e.target.value)}
              placeholder="Ej. Auditorio"
              className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2"
            />
          </label>
        </div>
      </section>

      {isLoading ? (
        <div className="text-gray-500">Cargando ocupación...</div>
      ) : groupedByDay.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-6 text-gray-600">
          No hay slots para los filtros seleccionados.
        </div>
      ) : (
        <div className="space-y-4">
          {groupedByDay.map(([day, slots]) => (
            <section key={day} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-100 bg-gray-50 flex items-center gap-2">
                <CalendarDays className="w-4 h-4 text-gray-600" />
                <h3 className="font-semibold text-gray-900">{formatDateOnlyLocal(day)}</h3>
                <span className="text-xs text-gray-500">· {slots.length} slots</span>
              </div>

              <div className="p-4 border-b border-gray-100 bg-gray-50/30">
                <h4 className="text-sm font-semibold text-gray-800">Timeline por espacio (bloques)</h4>
                <p className="text-xs text-gray-500 mb-3">
                  Franjas fusionadas por evento/reserva o disponibilidad continua (misma vista conceptual que Control Center).
                </p>
                <div className="space-y-2">
                  <div className="grid grid-cols-[220px_1fr] gap-2 text-[11px] text-gray-500">
                    <div />
                    <div className="relative h-5">
                      {Array.from({ length: DAY_END_HOUR - DAY_START_HOUR + 1 }).map((_, idx) => {
                        const hour = DAY_START_HOUR + idx;
                        const pct = (idx / (DAY_END_HOUR - DAY_START_HOUR)) * 100;
                        return (
                          <span
                            key={hour}
                            className="absolute -translate-x-1/2"
                            style={{ left: `${pct}%` }}
                          >
                            {String(hour).padStart(2, '0')}:00
                          </span>
                        );
                      })}
                    </div>
                  </div>

                  {Array.from(new Set(slots.map((s) => s.space_name)))
                    .sort((a, b) => a.localeCompare(b, 'es'))
                    .map((spaceName) => {
                      const rowSlots = slots
                        .filter((s) => s.space_name === spaceName)
                        .sort((a, b) => timeToMinutes(a.hora_inicio) - timeToMinutes(b.hora_inicio));
                      const blocks = mergeSlotsToBlocks(rowSlots);
                      return (
                        <div key={spaceName} className="grid grid-cols-[220px_1fr] gap-2 items-center">
                          <div className="text-xs font-medium text-gray-700 truncate">{spaceName}</div>
                          <div className="relative h-8 rounded bg-white border border-gray-200 overflow-hidden">
                            {Array.from({ length: DAY_END_HOUR - DAY_START_HOUR + 1 }).map((_, idx) => {
                              const pct = (idx / (DAY_END_HOUR - DAY_START_HOUR)) * 100;
                              return (
                                <div
                                  key={idx}
                                  className="absolute top-0 bottom-0 w-px bg-gray-100"
                                  style={{ left: `${pct}%` }}
                                />
                              );
                            })}
                            {blocks.map((block, bi) => {
                              const representative =
                                block.slots.find((s) => s.reservation_id) ?? block.slots[0];
                              const eventLabel =
                                representative.event_name ||
                                representative.related_event_name ||
                                (representative.group_event_id
                                  ? `Evento ${representative.group_event_id.slice(0, 8)}`
                                  : 'Sin evento');
                              const resSt = representative.reservation_status;
                              const occLabel = statusLabel(representative.occupancy_status);
                              const mergeHint =
                                block.slots.length > 1 ? ` · ${block.slots.length} slots fusionados` : '';
                              const title = `${block.hora_inicio.slice(0, 5)}–${block.hora_fin.slice(0, 5)} · ${occLabel}${
                                resSt ? ` · ${resSt}` : ''
                              } · ${eventLabel}${mergeHint}`;
                              return (
                                <button
                                  key={`${spaceName}-${bi}-${block.hora_inicio}`}
                                  type="button"
                                  className={`absolute top-1 bottom-1 rounded-md ${blockVisualClass(block)} opacity-95 hover:opacity-100 shadow-sm`}
                                  style={{
                                    left: `${leftPct(block.hora_inicio)}%`,
                                    width: `${Math.max(1.2, widthPct(block.hora_inicio, block.hora_fin))}%`,
                                  }}
                                  title={title}
                                  onClick={() => setSelectedSlot(representative)}
                                />
                              );
                            })}
                          </div>
                        </div>
                      );
                    })}
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[980px]">
                  <thead>
                    <tr className="text-left text-gray-700 bg-gray-50 border-b border-gray-200">
                      <th className="px-4 py-2 font-semibold">Espacio</th>
                      <th className="px-4 py-2 font-semibold">Horario</th>
                      <th className="px-4 py-2 font-semibold">Duración</th>
                      <th className="px-4 py-2 font-semibold">Estado</th>
                      <th className="px-4 py-2 font-semibold">Evento</th>
                      <th className="px-4 py-2 font-semibold">Cliente / Responsable</th>
                    </tr>
                  </thead>
                  <tbody>
                    {slots.map((slot) => (
                      <tr key={slot.slot_id} className="border-b border-gray-100">
                        <td className="px-4 py-2">
                          <div className="flex items-center gap-2">
                            <Building2 className="w-4 h-4 text-gray-400" />
                            <div className="min-w-0">
                              <span className="font-medium text-gray-900">{slot.space_name}</span>
                              {(slot.slot_status === 'BLOCKED_BY_PARENT' || slot.slot_status === 'BLOCKED_BY_CHILD') && (
                                <div className="text-[11px] text-amber-700">
                                  Dependiente de {slot.related_space_name || 'espacio relacionado'}
                                </div>
                              )}
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-2 text-gray-700">
                          <span className="inline-flex items-center gap-1">
                            <Clock3 className="w-4 h-4 text-gray-400" />
                            {slot.hora_inicio.slice(0, 5)} - {slot.hora_fin.slice(0, 5)}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-gray-700">{slot.duracion_horas} h</td>
                        <td className="px-4 py-2">
                          <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${statusChip(slot.occupancy_status)}`}>
                            {statusLabel(slot.occupancy_status)}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-gray-700">
                          {slot.event_name ||
                            slot.related_event_name ||
                            (slot.group_event_id ? `Evento ${slot.group_event_id.slice(0, 8).toUpperCase()}` : '—')}
                        </td>
                        <td className="px-4 py-2 text-gray-700">
                          <div className="inline-flex items-center gap-1">
                            <UserRound className="w-4 h-4 text-gray-400" />
                            {slot.customer_name || slot.customer_email || slot.related_customer_name || '—'}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ))}
        </div>
      )}

      {selectedSlot && (
        <>
          <div
            className="fixed inset-0 bg-black/30 z-40"
            onClick={() => setSelectedSlot(null)}
            aria-hidden
          />
          <aside className="fixed top-0 right-0 h-full w-full max-w-md bg-white border-l border-gray-200 shadow-2xl z-50 overflow-y-auto">
            <div className="sticky top-0 bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between">
              <h3 className="font-semibold text-gray-900">Detalle del slot</h3>
              <button
                type="button"
                className="p-2 rounded hover:bg-gray-100"
                onClick={() => setSelectedSlot(null)}
                aria-label="Cerrar panel"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-4 space-y-4 text-sm">
              <div>
                <p className="text-gray-500">Espacio</p>
                <p className="font-medium text-gray-900">{selectedSlot.space_name}</p>
              </div>
              <div>
                <p className="text-gray-500">Fecha y horario</p>
                <p className="font-medium text-gray-900">
                  {formatDateOnlyLocal(selectedSlot.fecha)} · {selectedSlot.hora_inicio.slice(0, 5)} - {selectedSlot.hora_fin.slice(0, 5)}
                </p>
              </div>
              <div>
                <p className="text-gray-500">Estado</p>
                <span className={`inline-block mt-1 px-2 py-0.5 rounded text-xs font-medium ${statusChip(selectedSlot.occupancy_status)}`}>
                  {statusLabel(selectedSlot.occupancy_status)}
                </span>
              </div>
              <div>
                <p className="text-gray-500">Evento</p>
                <p className="font-medium text-gray-900">
                  {selectedSlot.event_name ||
                    selectedSlot.related_event_name ||
                    (selectedSlot.group_event_id ? `Evento ${selectedSlot.group_event_id.slice(0, 8).toUpperCase()}` : 'Sin evento')}
                </p>
              </div>
              <div>
                <p className="text-gray-500">Cliente / responsable</p>
                <p className="font-medium text-gray-900">
                  {selectedSlot.customer_name ||
                    selectedSlot.customer_email ||
                    selectedSlot.related_customer_name ||
                    '—'}
                </p>
              </div>
              {(selectedSlot.slot_status === 'BLOCKED_BY_PARENT' || selectedSlot.slot_status === 'BLOCKED_BY_CHILD') && (
                <div>
                  <p className="text-gray-500">Dependencia de espacio</p>
                  <p className="font-medium text-amber-700">
                    {selectedSlot.related_space_name
                      ? `Bloqueado por ocupación de ${selectedSlot.related_space_name}`
                      : 'Bloqueado por relación parent/child de espacios'}
                  </p>
                </div>
              )}
              <div>
                <p className="text-gray-500">IDs</p>
                <div className="space-y-2 mt-1">
                  <div className="flex items-center justify-between gap-2 rounded border border-gray-200 p-2">
                    <span className="text-xs text-gray-600 truncate">Reserva: {selectedSlot.reservation_id || '—'}</span>
                    {selectedSlot.reservation_id && (
                      <button
                        type="button"
                        className="inline-flex items-center gap-1 text-xs text-blue-700 hover:text-blue-900"
                        onClick={() => navigator.clipboard.writeText(selectedSlot.reservation_id!)}
                      >
                        <Copy className="w-3 h-3" />
                        Copiar
                      </button>
                    )}
                  </div>
                  <div className="flex items-center justify-between gap-2 rounded border border-gray-200 p-2">
                    <span className="text-xs text-gray-600 truncate">Evento: {selectedSlot.group_event_id || '—'}</span>
                    {selectedSlot.group_event_id && (
                      <button
                        type="button"
                        className="inline-flex items-center gap-1 text-xs text-blue-700 hover:text-blue-900"
                        onClick={() => navigator.clipboard.writeText(selectedSlot.group_event_id!)}
                      >
                        <Copy className="w-3 h-3" />
                        Copiar
                      </button>
                    )}
                  </div>
                </div>
              </div>

              {selectedSlot.reservation_id && (
                <a
                  href={`/my-events/${selectedSlot.reservation_id}`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700"
                >
                  <ExternalLink className="w-4 h-4" />
                  Abrir detalle de reserva
                </a>
              )}
            </div>
          </aside>
        </>
      )}
    </div>
  );
}

export default function OccupancyPage() {
  return (
    <RoleGuard allowedRoles={CAN_ACCESS_STAFF_MONITOR}>
      <OccupancyContent />
    </RoleGuard>
  );
}

