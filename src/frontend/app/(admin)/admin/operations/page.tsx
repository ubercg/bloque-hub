'use client';

/**
 * Control Center operativo: vista por evento/reserva (bloques fusionados), KPIs, timeline y readiness.
 * Datos: GET /operations/reservations-summary. Acciones: bulk generate-slip, cancel (reglas del API).
 */

import { Fragment, useCallback, useMemo, useState } from 'react';
import useSWR from 'swr';
import Link from 'next/link';
import { toast } from 'sonner';
import {
  CAN_ACCESS_OPERATIONS,
  CAN_ACCESS_STAFF_MONITOR,
  RoleGuard,
  useAuthStore,
} from '@/features/auth';
import { EventSpaceSummary, type EventSummarySpace } from '@/features/portal/EventSpaceSummary';
import apiClient from '@/lib/http/apiClient';
import {
  getDateRangeInclusive,
  formatDateOnlyShort,
  formatDateOnlyLocal,
  monthRangeMexico,
} from '@/lib/dateUtils';

interface Reservation {
  id: string;
  tenant_id: string;
  user_id: string;
  space_id: string;
  fecha: string;
  hora_inicio: string;
  hora_fin: string;
  status: string;
  created_at: string;
  updated_at: string;
  group_event_id?: string | null;
}

interface Space {
  id: string;
  name: string;
  slug: string;
  piso: number | null;
}

interface Readiness {
  is_ready: boolean;
  checklist_pct: number;
  evidence_complete: boolean;
  details: {
    pending_critical_items: { id: string; title: string }[];
    pending_evidence: { id: string; tipo_documento: string }[];
  };
}

interface EvidenceRequirement {
  id: string;
  master_service_order_id: string;
  tipo_documento: string;
  estado: string;
  filename: string | null;
  file_size_bytes: number | null;
  uploaded_at: string | null;
  revisado_at: string | null;
  motivo_rechazo: string | null;
}

interface TimeBlock {
  date: string;
  start: string;
  end: string;
  hours: number;
  reservation_ids: string[];
}

interface SpaceBlocks {
  space_id: string;
  name: string;
  blocks: TimeBlock[];
}

interface ReservationGroup {
  operational_group_id: string;
  group_event_id: string | null;
  reservation_ids: string[];
  event_name: string | null;
  date_from: string;
  date_to: string;
  status: string;
  status_is_mixed: boolean;
  spaces: SpaceBlocks[];
  readiness: {
    documents: boolean;
    payment: boolean;
    validation: boolean | null;
  };
}

interface SummaryResponse {
  kpis: {
    events_today: number;
    spaces_occupied_today: number;
    pending_slip_groups_today: number;
    confirmed_groups_today: number;
  };
  reservations: ReservationGroup[];
}

/** Respuesta GET /reservations/{id}/event-summary (sin importes). */
interface EventSummaryApiResponse {
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

interface ExpedienteDocument {
  id: string;
  group_event_id: string;
  document_type_code: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  status: string;
  created_at: string;
}

interface CompletenessApi {
  required: Array<{ type: string; label: string; status: string; document_id: string | null }>;
  optional: Array<{ type: string; label: string; status: string; document_id: string | null }>;
  is_complete: boolean;
}

const fetcher = (url: string) => apiClient.get(url).then((r) => r.data);

function parseHm(m: string): number {
  const [h, min] = m.split(':').map((x) => parseInt(x, 10));
  return h * 60 + (min || 0);
}

function statusBarClass(status: string): string {
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

function statusLabel(status: string, mixed: boolean): string {
  const labels: Record<string, string> = {
    PENDING_SLIP: 'Pendiente pase de caja',
    AWAITING_PAYMENT: 'Esperando pago',
    PAYMENT_UNDER_REVIEW: 'Pago en revisión',
    CONFIRMED: 'Confirmada',
    EXPIRED: 'Expirada',
    CANCELLED: 'Cancelada',
  };
  const base = labels[status] ?? status;
  return mixed ? `${base} (mixto)` : base;
}

function OperationsContent() {
  const [dateFrom, setDateFrom] = useState(() => monthRangeMexico().from);
  const [dateTo, setDateTo] = useState(() => monthRangeMexico().to);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [spaceFilter, setSpaceFilter] = useState<string>('');
  const [selectedReservationId, setSelectedReservationId] = useState<string | null>(null);
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);
  const [confirmModal, setConfirmModal] = useState<{ group: ReservationGroup } | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  /** Ancla + slots del grupo para resumen de evento (sin precios). */
  const [eventSummaryContext, setEventSummaryContext] = useState<{
    anchorId: string;
    slotIds: string[];
  } | null>(null);
  const [expedienteGroup, setExpedienteGroup] = useState<ReservationGroup | null>(null);
  const [slipPreviewGroup, setSlipPreviewGroup] = useState<ReservationGroup | null>(null);
  const [slipPreviewItems, setSlipPreviewItems] = useState<{ reservation_id: string; html: string }[] | null>(null);
  const [slipPreviewLoading, setSlipPreviewLoading] = useState(false);

  const role = useAuthStore((s) => s.user?.role);
  const canManageSlip = role === 'COMMERCIAL' || role === 'FINANCE' || role === 'SUPERADMIN';
  const canCancel =
    role != null && (CAN_ACCESS_STAFF_MONITOR as readonly string[]).includes(role);

  const summaryParams = new URLSearchParams();
  if (dateFrom) summaryParams.set('date_from', dateFrom);
  if (dateTo) summaryParams.set('date_to', dateTo);
  if (statusFilter) summaryParams.set('status', statusFilter);
  if (spaceFilter) summaryParams.set('space_id', spaceFilter);

  const summaryKey = `/operations/reservations-summary?${summaryParams.toString()}`;
  const { data: summary, mutate: mutateSummary, isLoading: summaryLoading } = useSWR<SummaryResponse>(
    summaryKey,
    fetcher,
    { refreshInterval: 30000 }
  );

  const { data: spaces = [] } = useSWR<Space[]>('/spaces', fetcher);
  const spaceMap = useMemo(() => new Map(spaces.map((s) => [s.id, s])), [spaces]);

  const { data: detailReservation, isLoading: detailLoading } = useSWR<Reservation>(
    selectedReservationId ? `/reservations/${selectedReservationId}` : null,
    fetcher
  );

  const { data: eventSummaryData, isLoading: eventSummaryLoading } = useSWR<EventSummaryApiResponse>(
    eventSummaryContext ? `/reservations/${eventSummaryContext.anchorId}/event-summary` : null,
    fetcher
  );

  const { data: slotDetailsForSummary = [] } = useSWR<Reservation[]>(
    eventSummaryContext ? ['slot-reservations', eventSummaryContext.slotIds.join(',')] : null,
    async () => {
      const ids = eventSummaryContext!.slotIds;
      if (ids.length === 0) return [];
      return Promise.all(ids.map((id) => apiClient.get<Reservation>(`/reservations/${id}`).then((r) => r.data)));
    }
  );

  const expedienteGroupId = expedienteGroup
    ? expedienteGroup.group_event_id ?? expedienteGroup.reservation_ids[0]
    : null;

  const { data: expedienteDocs = [], isLoading: expedienteDocsLoading } = useSWR<ExpedienteDocument[]>(
    expedienteGroupId ? `/group-events/${expedienteGroupId}/documents` : null,
    fetcher
  );
  const { data: expedienteCompleteness } = useSWR<CompletenessApi>(
    expedienteGroupId ? `/group-events/${expedienteGroupId}/documents/completeness` : null,
    fetcher
  );

  const dateRange = useMemo(() => getDateRangeInclusive(dateFrom, dateTo), [dateFrom, dateTo]);

  /** Timeline: merge blocks per space from all groups (for current filters). */
  const ganttRows = useMemo(() => {
    const bySpace = new Map<
      string,
      {
        space: { id: string; name: string; piso: number | null };
        segments: {
          date: string;
          start: string;
          end: string;
          status: string;
          label: string;
          operational_group_id: string;
          anchor_reservation_id: string;
        }[];
      }
    >();
    for (const row of summary?.reservations ?? []) {
      const label = row.event_name?.trim() || row.operational_group_id.slice(0, 8);
      for (const sp of row.spaces) {
        const sm = spaceMap.get(sp.space_id);
        if (!bySpace.has(sp.space_id)) {
          bySpace.set(sp.space_id, {
            space: {
              id: sp.space_id,
              name: sp.name,
              piso: sm?.piso ?? null,
            },
            segments: [],
          });
        }
        for (const b of sp.blocks) {
          const anchor = b.reservation_ids[0] ?? row.reservation_ids[0];
          if (!anchor) continue;
          bySpace.get(sp.space_id)!.segments.push({
            date: b.date,
            start: b.start,
            end: b.end,
            status: row.status,
            label,
            operational_group_id: row.operational_group_id,
            anchor_reservation_id: anchor,
          });
        }
      }
    }
    return Array.from(bySpace.values()).sort((a, b) => (a.space.piso ?? 0) - (b.space.piso ?? 0));
  }, [summary, spaceMap]);

  const DAYS_PER_PAGE = 7;
  const SPACES_PER_PAGE = 12;
  const [dayPage, setDayPage] = useState(0);
  const [spacePage, setSpacePage] = useState(0);
  const maxDayPage = Math.max(0, Math.ceil(dateRange.length / DAYS_PER_PAGE) - 1);
  const maxSpacePage = Math.max(0, Math.ceil(ganttRows.length / SPACES_PER_PAGE) - 1);
  const dateRangeSlice = dateRange.slice(dayPage * DAYS_PER_PAGE, (dayPage + 1) * DAYS_PER_PAGE);
  const ganttRowsSlice = ganttRows.slice(spacePage * SPACES_PER_PAGE, (spacePage + 1) * SPACES_PER_PAGE);

  const runBulkSlip = useCallback(
    async (group: ReservationGroup) => {
      setActionLoading(true);
      try {
        const body =
          group.group_event_id != null
            ? { group_event_id: group.group_event_id }
            : { reservation_ids: group.reservation_ids };
        await apiClient.post('/reservations/bulk/generate-slip', body);
        toast.success('Pase de Caja generado para todos los slots pendientes');
        setSlipPreviewGroup(null);
        setSlipPreviewItems(null);
        await mutateSummary();
      } catch (err: unknown) {
        const detail =
          err && typeof err === 'object' && 'response' in err
            ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
            : 'Error';
        toast.error(String(detail));
      } finally {
        setActionLoading(false);
      }
    },
    [mutateSummary]
  );

  const openSlipPreview = useCallback(async (group: ReservationGroup) => {
    setSlipPreviewLoading(true);
    setSlipPreviewItems(null);
    setSlipPreviewGroup(group);
    try {
      const body =
        group.group_event_id != null
          ? { group_event_id: group.group_event_id }
          : { reservation_ids: group.reservation_ids };
      const { data } = await apiClient.post<{ items: { reservation_id: string; html: string }[] }>(
        '/reservations/bulk/generate-slip-preview',
        body
      );
      setSlipPreviewItems(data.items);
      if (!data.items.length) {
        toast.info('No hay slots en PENDIENTE PASE para previsualizar');
      }
    } catch (err: unknown) {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : 'Error';
      toast.error(String(detail));
      setSlipPreviewGroup(null);
    } finally {
      setSlipPreviewLoading(false);
    }
  }, []);

  const openExpedienteFile = useCallback(async (groupId: string, documentId: string) => {
    try {
      const { data } = await apiClient.get(`/group-events/${groupId}/documents/${documentId}/file`, {
        responseType: 'blob',
      });
      const blob = data as Blob;
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank', 'noopener,noreferrer');
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch {
      toast.error('No se pudo abrir el archivo');
    }
  }, []);

  const runCancel = useCallback(
    async (group: ReservationGroup) => {
      const anchor = group.reservation_ids[0];
      if (!anchor) return;
      setActionLoading(true);
      try {
        await apiClient.post(`/reservations/${anchor}/cancel`);
        toast.success('Reserva cancelada');
        setConfirmModal(null);
        await mutateSummary();
      } catch (err: unknown) {
        const detail =
          err && typeof err === 'object' && 'response' in err
            ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
            : 'Error';
        toast.error(String(detail));
      } finally {
        setActionLoading(false);
      }
    },
    [mutateSummary]
  );

  const kpis = summary?.kpis;

  return (
    <div className="space-y-6 max-w-[1600px]">
      <h1 className="text-xl font-bold text-gray-900">Control Center</h1>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard title="Eventos hoy" value={kpis?.events_today ?? '—'} loading={summaryLoading} />
        <KpiCard title="Espacios ocupados hoy" value={kpis?.spaces_occupied_today ?? '—'} loading={summaryLoading} />
        <KpiCard title="Pendientes pase (hoy)" value={kpis?.pending_slip_groups_today ?? '—'} loading={summaryLoading} />
        <KpiCard title="Confirmados (hoy)" value={kpis?.confirmed_groups_today ?? '—'} loading={summaryLoading} />
      </div>

      <div className="flex flex-wrap gap-4 items-center">
        <label className="flex items-center gap-2">
          <span className="text-sm text-gray-600">Desde</span>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="border border-gray-300 rounded px-2 py-1 text-sm"
          />
        </label>
        <label className="flex items-center gap-2">
          <span className="text-sm text-gray-600">Hasta</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="border border-gray-300 rounded px-2 py-1 text-sm"
          />
        </label>
        <label className="flex items-center gap-2">
          <span className="text-sm text-gray-600">Estado</span>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="border border-gray-300 rounded px-2 py-1 text-sm min-w-[180px]"
          >
            <option value="">Todos</option>
            <option value="CONFIRMED">Confirmadas</option>
            <option value="PENDING_SLIP">Pendiente slip</option>
            <option value="AWAITING_PAYMENT">Esperando pago</option>
            <option value="PAYMENT_UNDER_REVIEW">En revisión</option>
            <option value="EXPIRED">Expiradas</option>
            <option value="CANCELLED">Canceladas</option>
          </select>
        </label>
        <label className="flex items-center gap-2">
          <span className="text-sm text-gray-600">Espacio</span>
          <select
            value={spaceFilter}
            onChange={(e) => setSpaceFilter(e.target.value)}
            className="border border-gray-300 rounded px-2 py-1 text-sm min-w-[200px]"
          >
            <option value="">Todos</option>
            {spaces.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      <section>
        <h2 className="text-lg font-semibold text-gray-800 mb-2">Reservas agrupadas</h2>
        <div className="border border-gray-200 rounded-lg overflow-x-auto">
          <table className="w-full text-sm text-left min-w-[900px]">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-3 py-2 font-medium text-gray-700 w-8" />
                <th className="px-3 py-2 font-medium text-gray-700">ID / Evento</th>
                <th className="px-3 py-2 font-medium text-gray-700">Espacios</th>
                <th className="px-3 py-2 font-medium text-gray-700">Fechas</th>
                <th className="px-3 py-2 font-medium text-gray-700">Horario</th>
                <th className="px-3 py-2 font-medium text-gray-700">Estado</th>
                <th className="px-3 py-2 font-medium text-gray-700">Listo</th>
                <th className="px-3 py-2 font-medium text-gray-700">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {(summary?.reservations ?? []).map((row) => {
                const open = expandedGroup === row.operational_group_id;
                const spaceNames = row.spaces.map((s) => s.name).join(', ');
                const schedule = row.spaces
                  .flatMap((s) =>
                    s.blocks.map((b) => `${formatDateOnlyLocal(b.date)} ${b.start}–${b.end}`)
                  )
                  .join('; ');
                const slipPending = row.status === 'PENDING_SLIP' && canManageSlip;
                return (
                  <Fragment key={row.operational_group_id}>
                    <tr className="border-b border-gray-100 hover:bg-gray-50/80">
                      <td className="px-3 py-2">
                        <button
                          type="button"
                          className="text-gray-500 hover:text-gray-800 text-xs"
                          onClick={() => setExpandedGroup(open ? null : row.operational_group_id)}
                          aria-expanded={open}
                        >
                          {open ? '▼' : '▶'}
                        </button>
                      </td>
                      <td className="px-3 py-2">
                        <div className="font-mono text-xs text-gray-500">{row.operational_group_id.slice(0, 8)}…</div>
                        <div className="text-gray-900 font-medium">{row.event_name ?? '—'}</div>
                      </td>
                      <td className="px-3 py-2 max-w-[200px] truncate" title={spaceNames}>
                        {spaceNames}
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap">
                        {formatDateOnlyLocal(row.date_from)}
                        {row.date_from !== row.date_to && (
                          <>
                            {' '}
                            → {formatDateOnlyLocal(row.date_to)}
                          </>
                        )}
                      </td>
                      <td className="px-3 py-2 text-xs max-w-[240px]" title={schedule}>
                        {schedule || '—'}
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium text-white ${statusBarClass(row.status)}`}
                        >
                          {statusLabel(row.status, row.status_is_mixed)}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <ReadinessMini r={row.readiness} />
                      </td>
                      <td className="px-3 py-2 space-x-1 flex flex-wrap gap-1">
                        <button
                          type="button"
                          className="px-2 py-1 rounded border border-gray-300 text-xs font-medium hover:bg-gray-50"
                          onClick={() =>
                            setEventSummaryContext({
                              anchorId: row.reservation_ids[0],
                              slotIds: row.reservation_ids,
                            })
                          }
                        >
                          Ver detalle
                        </button>
                        {slipPending && (
                          <button
                            type="button"
                            className="px-2 py-1 rounded bg-blue-600 text-white text-xs font-medium hover:bg-blue-700"
                            onClick={() => void openSlipPreview(row)}
                          >
                            Generar pase
                          </button>
                        )}
                        {canCancel && (row.status === 'PENDING_SLIP' || row.status === 'AWAITING_PAYMENT') && (
                          <button
                            type="button"
                            className="px-2 py-1 rounded bg-red-600 text-white text-xs font-medium hover:bg-red-700"
                            onClick={() => setConfirmModal({ group: row })}
                          >
                            Cancelar
                          </button>
                        )}
                        <button
                          type="button"
                          className="px-2 py-1 rounded border border-gray-300 text-xs font-medium hover:bg-gray-50 text-gray-800"
                          onClick={() => setExpedienteGroup(row)}
                        >
                          Expediente
                        </button>
                      </td>
                    </tr>
                    {open && (
                      <tr className="bg-gray-50/50">
                        <td colSpan={8} className="px-4 py-3 text-xs text-gray-600">
                          <p className="font-medium text-gray-800 mb-1">Slots ({row.reservation_ids.length})</p>
                          <ul className="font-mono space-y-1">
                            {row.reservation_ids.map((id) => (
                              <li key={id}>
                                {id.slice(0, 8)}…
                                <button
                                  type="button"
                                  className="ml-2 text-blue-600 hover:underline"
                                  onClick={() => setSelectedReservationId(id)}
                                >
                                  Abrir
                                </button>
                              </li>
                            ))}
                          </ul>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
          {summaryLoading && (
            <div className="p-4 text-center text-gray-500 text-sm">Cargando…</div>
          )}
          {!summaryLoading && (summary?.reservations?.length ?? 0) === 0 && (
            <div className="p-4 text-center text-gray-500 text-sm">Sin reservas en el rango y filtros seleccionados</div>
          )}
        </div>
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-1 gap-6">
        <div>
          <h2 className="text-lg font-semibold text-gray-800 mb-2">Timeline por espacio (bloques)</h2>
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <span className="text-sm text-gray-600">Días:</span>
            <button
              type="button"
              onClick={() => setDayPage((p) => Math.max(0, p - 1))}
              disabled={dayPage === 0}
              className="px-2 py-1 rounded border border-gray-300 text-sm disabled:opacity-50"
            >
              Anteriores
            </button>
            <span className="text-sm text-gray-700">
              {dateRange.length === 0
                ? '0'
                : `${dayPage * DAYS_PER_PAGE + 1}-${Math.min((dayPage + 1) * DAYS_PER_PAGE, dateRange.length)}`}{' '}
              de {dateRange.length}
            </span>
            <button
              type="button"
              onClick={() => setDayPage((p) => Math.min(maxDayPage, p + 1))}
              disabled={dayPage >= maxDayPage}
              className="px-2 py-1 rounded border border-gray-300 text-sm disabled:opacity-50"
            >
              Siguientes
            </button>
            <span className="text-sm text-gray-600 ml-2">Espacios:</span>
            <button
              type="button"
              onClick={() => setSpacePage((p) => Math.max(0, p - 1))}
              disabled={spacePage === 0}
              className="px-2 py-1 rounded border border-gray-300 text-sm disabled:opacity-50"
            >
              Anteriores
            </button>
            <span className="text-sm text-gray-700">
              {ganttRows.length === 0 ? '0' : `${spacePage * SPACES_PER_PAGE + 1}-${Math.min((spacePage + 1) * SPACES_PER_PAGE, ganttRows.length)}`}{' '}
              de {ganttRows.length}
            </span>
            <button
              type="button"
              onClick={() => setSpacePage((p) => Math.min(maxSpacePage, p + 1))}
              disabled={spacePage >= maxSpacePage}
              className="px-2 py-1 rounded border border-gray-300 text-sm disabled:opacity-50"
            >
              Siguientes
            </button>
          </div>
          <div className="border border-gray-200 rounded-lg overflow-x-auto">
            <div className="min-w-[600px]">
              <div className="grid grid-cols-[140px_1fr] border-b border-gray-200 bg-gray-50 text-sm">
                <div className="p-2 font-medium">Espacio</div>
                <div className="flex">
                  {dateRangeSlice.map((d) => (
                    <div key={d} className="flex-1 min-w-[80px] p-2 border-l border-gray-200">
                      {formatDateOnlyShort(d, { weekday: 'short', month: 'short' })}
                    </div>
                  ))}
                </div>
              </div>
              {ganttRowsSlice.map(({ space, segments }) => (
                <div key={space.id} className="grid grid-cols-[140px_1fr] border-b border-gray-100 hover:bg-gray-50/50">
                  <div className="p-2 text-sm truncate" title={space.name}>
                    {space.name}
                  </div>
                  <div className="flex relative min-h-[40px]">
                    {dateRangeSlice.map((d) => (
                      <div key={d} className="flex-1 min-w-[80px] border-l border-gray-100 relative" />
                    ))}
                    {segments.map((seg, idx) => {
                      const dayIndexFull = dateRange.findIndex((x) => x === seg.date);
                      const dayIndexInSlice = dayIndexFull - dayPage * DAYS_PER_PAGE;
                      if (dayIndexInSlice < 0 || dayIndexInSlice >= dateRangeSlice.length) return null;
                      const n = dateRangeSlice.length;
                      const dayW = 100 / n;
                      const startM = parseHm(seg.start);
                      const endM = parseHm(seg.end);
                      const span = Math.max(1, endM - startM);
                      const dayMin = 24 * 60;
                      const leftPct = dayIndexInSlice * dayW + (startM / dayMin) * dayW;
                      const widthPct = (span / dayMin) * dayW;
                      return (
                        <div
                          key={`${seg.operational_group_id}-${seg.date}-${idx}-${seg.start}`}
                          className={`absolute h-7 rounded text-white text-[10px] flex items-center justify-center truncate px-0.5 cursor-pointer hover:opacity-90 z-10 ${statusBarClass(seg.status)}`}
                          style={{
                            left: `${leftPct}%`,
                            width: `max(2px, ${widthPct}%)`,
                            top: 6,
                          }}
                          title={`${seg.label} · ${seg.start}–${seg.end}`}
                          onClick={() => {
                            const row = summary?.reservations.find(
                              (r) => r.operational_group_id === seg.operational_group_id
                            );
                            if (row?.reservation_ids.length) {
                              setEventSummaryContext({
                                anchorId: row.reservation_ids[0],
                                slotIds: row.reservation_ids,
                              });
                            }
                          }}
                        />
                      );
                    })}
                  </div>
                </div>
              ))}
              {ganttRows.length === 0 && !summaryLoading && (
                <div className="p-4 text-center text-gray-500 text-sm">Sin bloques en el rango seleccionado</div>
              )}
            </div>
          </div>
        </div>
      </div>

      {confirmModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6">
            <h3 className="text-lg font-bold text-gray-900 mb-2">Confirmar cancelación</h3>
            <p className="text-sm text-gray-600 mb-4">
              Evento: {confirmModal.group.event_name ?? confirmModal.group.operational_group_id.slice(0, 8)}
            </p>
            <p className="text-sm text-red-700 bg-red-50 rounded p-3 mb-4">
              {confirmModal.group.group_event_id != null ? (
                <>
                  Se cancelará el <strong>evento completo</strong> ({confirmModal.group.reservation_ids.length}{' '}
                  reservas vinculadas al mismo grupo). No se puede deshacer.
                </>
              ) : (
                <>
                  Se cancelará <strong>1 reserva</strong> (sin grupo de evento). No se puede deshacer.
                </>
              )}
            </p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setConfirmModal(null)}
                className="px-4 py-2 rounded border border-gray-300 text-gray-700 font-medium hover:bg-gray-50"
              >
                Volver
              </button>
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => runCancel(confirmModal.group)}
                className="px-4 py-2 rounded font-medium text-white disabled:opacity-50 bg-red-600 hover:bg-red-700"
              >
                {actionLoading ? 'Procesando…' : 'Cancelar evento'}
              </button>
            </div>
          </div>
        </div>
      )}

      {eventSummaryContext && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-3xl w-full max-h-[90vh] flex flex-col p-6">
            <div className="flex justify-between items-start gap-4 mb-4">
              <div>
                <h3 className="text-lg font-bold text-gray-900">Resumen del evento</h3>
                {eventSummaryData && (
                  <p className="text-sm text-gray-600 mt-1">
                    {eventSummaryData.event.name?.trim() || '—'} ·{' '}
                    {eventSummaryData.totals.unique_spaces} espacio(s) · {eventSummaryData.totals.total_hours.toFixed(1)}{' '}
                    h totales
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={() => setEventSummaryContext(null)}
                className="text-gray-500 hover:text-gray-800 shrink-0"
              >
                Cerrar
              </button>
            </div>
            <div className="overflow-y-auto flex-1 min-h-0 pr-1">
              {eventSummaryLoading && <p className="text-sm text-gray-500">Cargando resumen…</p>}
              {!eventSummaryLoading && eventSummaryData && (
                <EventSpaceSummary
                  spaces={eventSummaryData.spaces}
                  flatReservations={slotDetailsForSummary.map((r) => ({
                    id: r.id,
                    fecha: r.fecha,
                    hora_inicio: r.hora_inicio,
                    hora_fin: r.hora_fin,
                    status: r.status,
                  }))}
                />
              )}
            </div>
          </div>
        </div>
      )}

      {expedienteGroup && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-lg w-full max-h-[90vh] flex flex-col p-6">
            <div className="flex justify-between items-start gap-4 mb-4">
              <div>
                <h3 className="text-lg font-bold text-gray-900">Expediente KYC</h3>
                <p className="text-sm text-gray-600 mt-1">
                  {expedienteGroup.event_name ?? expedienteGroup.operational_group_id.slice(0, 8)}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setExpedienteGroup(null)}
                className="text-gray-500 hover:text-gray-800 shrink-0"
              >
                Cerrar
              </button>
            </div>
            {expedienteCompleteness && (
              <div className="mb-4 text-sm">
                <p className="font-medium text-gray-800 mb-1">
                  Completitud: {expedienteCompleteness.is_complete ? 'Completa' : 'Pendiente'}
                </p>
                <ul className="text-xs text-gray-600 space-y-1 max-h-24 overflow-y-auto">
                  {expedienteCompleteness.required.map((r) => (
                    <li key={`req-${r.type}`}>
                      {r.label}: {r.status}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div className="overflow-y-auto flex-1 min-h-0">
              {expedienteDocsLoading && <p className="text-sm text-gray-500">Cargando documentos…</p>}
              {!expedienteDocsLoading && expedienteDocs.length === 0 && (
                <p className="text-sm text-gray-600">No hay documentos registrados para este grupo.</p>
              )}
              <ul className="space-y-2">
                {expedienteDocs.map((doc) => (
                  <li
                    key={doc.id}
                    className="flex flex-wrap items-center justify-between gap-2 p-2 rounded border border-gray-100 bg-gray-50 text-sm"
                  >
                    <div>
                      <span className="font-medium text-gray-800">{doc.document_type_code}</span>
                      <span className="text-gray-500 text-xs block truncate max-w-[320px]" title={doc.original_filename}>
                        {doc.original_filename}
                      </span>
                      <span className="text-xs text-gray-400">
                        {new Date(doc.created_at).toLocaleString('es-MX')} · {(doc.size_bytes / 1024).toFixed(1)} KB
                      </span>
                    </div>
                    {expedienteGroupId && (
                      <button
                        type="button"
                        onClick={() => void openExpedienteFile(expedienteGroupId, doc.id)}
                        className="px-2 py-1 rounded border border-gray-300 text-xs font-medium hover:bg-white"
                      >
                        Abrir
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </div>
            <p className="text-xs text-gray-500 mt-4">
              <Link href={`/my-events/${expedienteGroup.reservation_ids[0]}`} className="text-blue-600 hover:underline">
                Ver en portal del cliente
              </Link>
            </p>
          </div>
        </div>
      )}

      {slipPreviewGroup && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-4xl w-full max-h-[92vh] flex flex-col p-6">
            <div className="flex justify-between items-start gap-4 mb-4">
              <div>
                <h3 className="text-lg font-bold text-gray-900">Previsualización — Pase de caja</h3>
                <p className="text-sm text-gray-600 mt-1">
                  {slipPreviewGroup.event_name ?? slipPreviewGroup.operational_group_id.slice(0, 8)} — correo por slot
                  pendiente
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setSlipPreviewGroup(null);
                  setSlipPreviewItems(null);
                }}
                className="text-gray-500 hover:text-gray-800 shrink-0"
              >
                Cerrar
              </button>
            </div>
            <div className="overflow-y-auto flex-1 min-h-0 space-y-6 border border-gray-100 rounded-lg p-4 bg-gray-50">
              {slipPreviewLoading && <p className="text-sm text-gray-600">Generando vista previa…</p>}
              {!slipPreviewLoading &&
                slipPreviewItems?.map((item) => (
                  <div key={item.reservation_id} className="border border-gray-200 rounded-lg overflow-hidden bg-white">
                    <p className="text-xs font-mono text-gray-500 px-3 py-2 bg-gray-100 border-b border-gray-200">
                      {item.reservation_id}
                    </p>
                    <div
                      className="p-3 text-sm max-w-none [&_a]:text-blue-600 [&_table]:w-full"
                      dangerouslySetInnerHTML={{ __html: item.html }}
                    />
                  </div>
                ))}
              {!slipPreviewLoading && slipPreviewItems && slipPreviewItems.length === 0 && (
                <p className="text-sm text-gray-600">No hay contenido de previsualización.</p>
              )}
            </div>
            <div className="flex justify-end gap-2 mt-4 pt-4 border-t border-gray-200">
              <button
                type="button"
                onClick={() => {
                  setSlipPreviewGroup(null);
                  setSlipPreviewItems(null);
                }}
                className="px-4 py-2 rounded border border-gray-300 text-gray-700 font-medium hover:bg-gray-50"
              >
                Volver
              </button>
              <button
                type="button"
                disabled={actionLoading || slipPreviewLoading || !slipPreviewItems?.length}
                onClick={() => slipPreviewGroup && runBulkSlip(slipPreviewGroup)}
                className="px-4 py-2 rounded font-medium text-white disabled:opacity-50 bg-blue-600 hover:bg-blue-700"
              >
                {actionLoading ? 'Enviando…' : 'Confirmar y enviar'}
              </button>
            </div>
          </div>
        </div>
      )}

      {selectedReservationId && detailLoading && (
        <div className="fixed right-0 top-0 bottom-0 w-full max-w-md bg-white border-l border-gray-200 shadow-xl z-30 flex items-center justify-center p-6">
          <p className="text-sm text-gray-600">Cargando detalle…</p>
        </div>
      )}
      {selectedReservationId && detailReservation && (
        <ReservationDetailPanel
          reservation={detailReservation}
          space={spaceMap.get(detailReservation.space_id)}
          onClose={() => setSelectedReservationId(null)}
        />
      )}
    </div>
  );
}

function KpiCard({ title, value, loading }: { title: string; value: number | string; loading: boolean }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{title}</p>
      <p className="text-2xl font-semibold text-gray-900 mt-1">{loading ? '…' : value}</p>
    </div>
  );
}

function ReadinessMini({
  r,
}: {
  r: { documents: boolean; payment: boolean; validation: boolean | null };
}) {
  const Item = ({ ok, label }: { ok: boolean | null; label: string }) => (
    <span className="inline-flex items-center gap-0.5 mr-2" title={label}>
      <span className="text-[10px] text-gray-500">{label}</span>
      {ok === null ? <span className="text-gray-400">n/d</span> : ok ? <span className="text-green-600">✓</span> : <span className="text-red-500">✗</span>}
    </span>
  );
  return (
    <div className="flex flex-wrap gap-0">
      <Item ok={r.documents} label="Doc" />
      <Item ok={r.payment} label="Pago" />
      <Item ok={r.validation} label="Op." />
    </div>
  );
}

const serviceOrderFetcher = (url: string) =>
  apiClient.get(url).then((r) => r.data).catch((err) => {
    if (err.response?.status === 404) return null;
    throw err;
  });

function EvidenceReviewSection({ reservationId }: { reservationId: string }) {
  const { data: orderData } = useSWR<{ id: string } | null>(
    `/reservations/${reservationId}/service-order`,
    serviceOrderFetcher
  );
  const { data: evidenceList = [], mutate: mutateEvidence } = useSWR<EvidenceRequirement[]>(
    orderData != null ? `/reservations/${reservationId}/evidence-requirements` : null,
    fetcher
  );
  const [rejectModal, setRejectModal] = useState<{
    evidenceId: string;
    tipoDocumento: string;
  } | null>(null);
  const [motivoRechazo, setMotivoRechazo] = useState('');
  const [loading, setLoading] = useState(false);

  const orderId = orderData?.id;

  const handleApprove = useCallback(
    async (evidenceId: string) => {
      setLoading(true);
      try {
        await apiClient.patch(`/service-order-evidence/${evidenceId}`, {
          estado: 'APROBADO',
        });
        toast.success('Documento aprobado');
        mutateEvidence();
      } catch (err: unknown) {
        const detail =
          err && typeof err === 'object' && 'response' in err
            ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
            : 'Error';
        toast.error(String(detail));
      } finally {
        setLoading(false);
      }
    },
    [mutateEvidence]
  );

  const handleRejectSubmit = useCallback(async () => {
    if (!rejectModal || !motivoRechazo.trim()) return;
    setLoading(true);
    try {
      await apiClient.patch(`/service-order-evidence/${rejectModal.evidenceId}`, {
        estado: 'RECHAZADO',
        motivo_rechazo: motivoRechazo.trim(),
      });
      toast.success('Documento rechazado');
      setRejectModal(null);
      setMotivoRechazo('');
      mutateEvidence();
    } catch (err: unknown) {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : 'Error';
      toast.error(String(detail));
    } finally {
      setLoading(false);
    }
  }, [rejectModal, motivoRechazo, mutateEvidence]);

  const handleDownload = useCallback(
    async (evId: string, filename: string | null) => {
      if (!orderId) return;
      try {
        const { data } = await apiClient.get(`/service-orders/${orderId}/evidence/${evId}/download`, {
          responseType: 'blob',
        });
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
    [orderId]
  );

  const formatTipo = (t: string) => t.replace(/_/g, ' ');
  const estadoLabel: Record<string, string> = {
    PENDIENTE: 'Pendiente',
    PENDIENTE_REVISION: 'En revisión',
    APROBADO: 'Aprobado',
    RECHAZADO: 'Rechazado',
  };

  if (evidenceList.length === 0) return null;

  return (
    <div className="pt-2 border-t">
      <p className="text-sm font-medium text-gray-800 mb-2">Documentos requeridos (Buzón)</p>
      <ul className="space-y-2">
        {evidenceList.map((ev) => (
          <li
            key={ev.id}
            className="flex flex-wrap items-center gap-2 p-2 rounded bg-gray-50 border border-gray-100 text-sm"
          >
            <span className="font-medium text-gray-800">{formatTipo(ev.tipo_documento)}</span>
            <span
              className={`px-2 py-0.5 rounded text-xs ${
                ev.estado === 'APROBADO'
                  ? 'bg-green-100 text-green-800'
                  : ev.estado === 'RECHAZADO'
                    ? 'bg-red-100 text-red-800'
                    : ev.estado === 'PENDIENTE_REVISION'
                      ? 'bg-amber-100 text-amber-800'
                      : 'bg-gray-200 text-gray-700'
              }`}
            >
              {estadoLabel[ev.estado] ?? ev.estado}
            </span>
            {ev.filename && (
              <span className="text-gray-500 truncate max-w-[140px]" title={ev.filename}>
                {ev.filename}
              </span>
            )}
            <div className="flex gap-1 ml-auto">
              {ev.filename && orderId && (
                <button
                  type="button"
                  onClick={() => handleDownload(ev.id, ev.filename)}
                  className="px-2 py-1 rounded border border-gray-300 text-xs font-medium hover:bg-gray-100 min-h-[32px]"
                  aria-label={`Descargar ${formatTipo(ev.tipo_documento)}`}
                >
                  Descargar
                </button>
              )}
              {ev.estado === 'PENDIENTE_REVISION' && (
                <>
                  <button
                    type="button"
                    onClick={() => handleApprove(ev.id)}
                    disabled={loading}
                    className="px-2 py-1 rounded bg-green-600 text-white text-xs font-medium hover:bg-green-700 disabled:opacity-50 min-h-[32px]"
                    aria-label={`Aprobar ${formatTipo(ev.tipo_documento)}`}
                  >
                    Aprobar
                  </button>
                  <button
                    type="button"
                    onClick={() => setRejectModal({ evidenceId: ev.id, tipoDocumento: ev.tipo_documento })}
                    disabled={loading}
                    className="px-2 py-1 rounded bg-red-600 text-white text-xs font-medium hover:bg-red-700 disabled:opacity-50 min-h-[32px]"
                    aria-label={`Rechazar ${formatTipo(ev.tipo_documento)}`}
                  >
                    Rechazar
                  </button>
                </>
              )}
            </div>
            {ev.estado === 'RECHAZADO' && ev.motivo_rechazo && (
              <p className="w-full text-xs text-red-600 mt-1">Motivo: {ev.motivo_rechazo}</p>
            )}
          </li>
        ))}
      </ul>
      {rejectModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6">
            <h4 className="font-semibold text-gray-900 mb-2">Rechazar documento: {formatTipo(rejectModal.tipoDocumento)}</h4>
            <p className="text-sm text-gray-600 mb-2">Indica el motivo del rechazo (obligatorio):</p>
            <textarea
              value={motivoRechazo}
              onChange={(e) => setMotivoRechazo(e.target.value)}
              placeholder="Ej: Documento ilegible, vigencia vencida..."
              className="w-full border border-gray-300 rounded-lg p-2 text-sm min-h-[80px]"
              rows={3}
            />
            <div className="flex justify-end gap-2 mt-4">
              <button
                type="button"
                onClick={() => {
                  setRejectModal(null);
                  setMotivoRechazo('');
                }}
                className="px-4 py-2 rounded border border-gray-300 text-gray-700 font-medium hover:bg-gray-50"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={handleRejectSubmit}
                disabled={loading || !motivoRechazo.trim()}
                className="px-4 py-2 rounded bg-red-600 text-white font-medium hover:bg-red-700 disabled:opacity-50"
              >
                {loading ? 'Enviando…' : 'Rechazar'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ReservationDetailPanel({
  reservation,
  space,
  onClose,
}: {
  reservation: Reservation;
  space?: Space;
  onClose: () => void;
}) {
  const { data: readiness } = useSWR<Readiness>(`/reservations/${reservation.id}/readiness`, fetcher, {
    refreshInterval: 30000,
  });

  return (
    <div className="fixed right-0 top-0 bottom-0 w-full max-w-md bg-white border-l border-gray-200 shadow-xl z-30 flex flex-col">
      <div className="p-4 border-b flex justify-between items-center">
        <h3 className="font-semibold text-gray-900">Detalle de reserva</h3>
        <button type="button" onClick={onClose} className="text-gray-500 hover:text-gray-700">
          Cerrar
        </button>
      </div>
      <div className="p-4 overflow-y-auto space-y-4">
        <p className="text-sm text-gray-600">
          <span className="font-medium">ID:</span> {reservation.id}
        </p>
        {space && (
          <p className="text-sm text-gray-600">
            <span className="font-medium">Espacio:</span> {space.name}
          </p>
        )}
        <p className="text-sm text-gray-600">
          <span className="font-medium">Fecha:</span> {formatDateOnlyLocal(reservation.fecha)} {reservation.hora_inicio} -{' '}
          {reservation.hora_fin}
        </p>
        <p className="text-sm text-gray-600">
          <span className="font-medium">Estado:</span> {reservation.status}
        </p>
        {readiness && (
          <div className="pt-2 border-t">
            <p className="text-sm font-medium text-gray-800 mb-1">Readiness</p>
            <p className="text-sm text-gray-600">
              Listo: {readiness.is_ready ? 'Sí' : 'No'} — Checklist: {readiness.checklist_pct.toFixed(0)}% — Evidencias:{' '}
              {readiness.evidence_complete ? 'Completas' : 'Pendientes'}
            </p>
          </div>
        )}
        <EvidenceReviewSection reservationId={reservation.id} />
      </div>
    </div>
  );
}

export default function OperationsPage() {
  return (
    <RoleGuard allowedRoles={[...CAN_ACCESS_OPERATIONS, 'COMMERCIAL', 'FINANCE']}>
      <OperationsContent />
    </RoleGuard>
  );
}
