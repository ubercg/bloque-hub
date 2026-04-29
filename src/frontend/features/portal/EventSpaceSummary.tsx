'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { parseDateOnlyAsLocal } from '@/lib/dateUtils';

export interface EventSummaryBlock {
  start: string;
  end: string;
  hours: number;
  reservation_ids: string[];
}

export interface EventSummaryDay {
  date: string;
  blocks: EventSummaryBlock[];
}

export interface EventSummarySpace {
  space_id: string;
  space_name: string;
  days: EventSummaryDay[];
}

export interface FlatReservationRow {
  id: string;
  fecha: string;
  hora_inicio: string;
  hora_fin: string;
  status: string;
}

const STATUS_LABELS: Record<string, string> = {
  PENDING_SLIP: 'Pre-reserva',
  AWAITING_PAYMENT: 'Esperando pago',
  PAYMENT_UNDER_REVIEW: 'En revisión',
  CONFIRMED: 'Confirmado',
  EXPIRED: 'Expirado',
  CANCELLED: 'Cancelado',
};

function statusBadgeClass(status: string): string {
  if (status === 'CONFIRMED') return 'bg-green-100 text-green-800';
  if (status === 'EXPIRED' || status === 'CANCELLED') return 'bg-gray-100 text-gray-600';
  if (status === 'PAYMENT_UNDER_REVIEW') return 'bg-purple-100 text-purple-800';
  if (status === 'AWAITING_PAYMENT') return 'bg-blue-100 text-blue-800';
  return 'bg-amber-100 text-amber-800';
}

function formatDayLabel(isoDate: string): string {
  return parseDateOnlyAsLocal(isoDate).toLocaleDateString('es-MX', {
    timeZone: 'America/Mexico_City',
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

export function EventSpaceSummary({
  spaces,
  flatReservations,
}: {
  spaces: EventSummarySpace[];
  flatReservations: FlatReservationRow[];
}) {
  const [openSpaces, setOpenSpaces] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {};
    for (const s of spaces) init[s.space_id] = true;
    return init;
  });
  const [detailOpen, setDetailOpen] = useState(false);

  const toggleSpace = (id: string) => {
    setOpenSpaces((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <div className="space-y-3">
      {spaces.map((space) => {
        const isOpen = openSpaces[space.space_id] !== false;
        return (
          <div key={space.space_id} className="border border-gray-200 rounded-xl overflow-hidden bg-white">
            <button
              type="button"
              onClick={() => toggleSpace(space.space_id)}
              className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-gray-50 min-h-[48px]"
            >
              <span className="font-semibold text-gray-900">{space.space_name}</span>
              {isOpen ? (
                <ChevronDown className="w-5 h-5 text-gray-500 flex-shrink-0" />
              ) : (
                <ChevronRight className="w-5 h-5 text-gray-500 flex-shrink-0" />
              )}
            </button>
            {isOpen && (
              <div className="px-4 pb-4 pt-0 border-t border-gray-100 space-y-4">
                {space.days.map((day) => (
                  <div key={day.date}>
                    <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                      {formatDayLabel(day.date)}
                    </p>
                    <ul className="space-y-2">
                      {day.blocks.map((b, idx) => (
                        <li
                          key={`${day.date}-${idx}-${b.start}`}
                          className="flex flex-wrap items-baseline justify-between gap-2 text-sm text-gray-800"
                        >
                          <span>
                            {b.start.slice(0, 5)} – {b.end.slice(0, 5)}
                          </span>
                          <span className="text-gray-600 tabular-nums">
                            {Number.isInteger(b.hours) ? b.hours : b.hours.toFixed(1)} h
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}

      <div className="pt-2">
        <button
          type="button"
          onClick={() => setDetailOpen(!detailOpen)}
          className="text-sm font-medium text-blue-600 hover:text-blue-800 min-h-[44px] py-2"
        >
          {detailOpen ? 'Ocultar detalle de slots' : 'Ver detalle (slots individuales)'}
        </button>
        {detailOpen && (
          <ul className="mt-2 space-y-2 border border-dashed border-gray-200 rounded-lg p-3 bg-gray-50/80 text-sm">
            {flatReservations.map((row) => (
              <li
                key={row.id}
                className="flex flex-wrap items-center justify-between gap-2 py-1 border-b border-gray-100 last:border-0"
              >
                <span className="text-gray-700">
                  {parseDateOnlyAsLocal(row.fecha).toLocaleDateString('es-MX', {
                    timeZone: 'America/Mexico_City',
                    day: '2-digit',
                    month: 'short',
                  })}{' '}
                  · {row.hora_inicio.slice(0, 5)} – {row.hora_fin.slice(0, 5)}
                </span>
                <span
                  className={`text-xs px-2 py-0.5 rounded font-medium ${statusBadgeClass(row.status)}`}
                >
                  {STATUS_LABELS[row.status] ?? row.status}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
