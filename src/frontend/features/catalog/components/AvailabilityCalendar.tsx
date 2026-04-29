'use client';

/**
 * AvailabilityCalendar — Monthly calendar view for space availability (FR-03, CA-01/CA-05)
 *
 * Color legend: Green = AVAILABLE, Grey = BLOCKED, Yellow = TTL_PENDING
 * Polling: SWR refreshInterval 5000ms for near-real-time updates (CA-05)
 * WCAG: aria-labels on slots, keyboard navigation, focus:ring-2
 */

import { useState, useMemo } from 'react';
import useSWR from 'swr';
import apiClient from '@/lib/http/apiClient';
import { formatDateOnlyLocal } from '@/lib/dateUtils';
import { ChevronLeft, ChevronRight } from 'lucide-react';

interface CalendarDaySlot {
  fecha: string;
  hora_inicio: string;
  hora_fin: string;
  status: 'AVAILABLE' | 'BLOCKED' | 'TTL_PENDING' | 'MAINTENANCE';
}

interface MonthAvailability {
  month: string;
  days: Record<string, CalendarDaySlot[]>;
}

interface Props {
  spaceId: string;
  sedeQuery?: string;
  onSlotSelect?: (slot: CalendarDaySlot) => void;
}

const fetcher = (url: string) => apiClient.get(url).then((r) => r.data);

const STATUS_COLORS: Record<string, { bg: string; border: string; label: string }> = {
  AVAILABLE: { bg: 'bg-green-100', border: 'border-green-400', label: 'Disponible' },
  BLOCKED: { bg: 'bg-gray-200', border: 'border-gray-400', label: 'No disponible' },
  TTL_PENDING: { bg: 'bg-yellow-100', border: 'border-yellow-400', label: 'En proceso' },
  MAINTENANCE: { bg: 'bg-gray-200', border: 'border-gray-400', label: 'No disponible' },
};

const DAY_NAMES = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];

const MONTH_NAMES = [
  'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
];

function formatTime(t: string): string {
  return t.slice(0, 5); // "09:00:00" → "09:00"
}

export default function AvailabilityCalendar({ spaceId, sedeQuery, onSlotSelect }: Props) {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1); // 1-based
  const [expandedDay, setExpandedDay] = useState<string | null>(null);

  const monthStr = `${year}-${String(month).padStart(2, '0')}`;
  const queryStr = sedeQuery ? `&${sedeQuery}` : '';
  const swrKey = `spaces/${spaceId}/availability?month=${monthStr}${queryStr}`;

  const { data, isLoading } = useSWR<MonthAvailability>(swrKey, fetcher, {
    refreshInterval: 5000,
    revalidateOnFocus: true,
    dedupingInterval: 3000,
  });

  // Navigate months
  const goNext = () => {
    const maxDate = new Date(today.getFullYear() + 1, today.getMonth() + 1, 1);
    const nextDate = new Date(year, month, 1); // month is 1-based so this is next month
    if (nextDate < maxDate) {
      if (month === 12) { setYear(year + 1); setMonth(1); }
      else setMonth(month + 1);
    }
    setExpandedDay(null);
  };

  const goPrev = () => {
    const minDate = new Date(today.getFullYear(), today.getMonth(), 1);
    const prevDate = new Date(year, month - 2, 1); // prev month
    if (prevDate >= minDate) {
      if (month === 1) { setYear(year - 1); setMonth(12); }
      else setMonth(month - 1);
    }
    setExpandedDay(null);
  };

  // Calendar grid computation
  const calendarWeeks = useMemo(() => {
    const firstDay = new Date(year, month - 1, 1);
    const lastDay = new Date(year, month, 0).getDate();
    // Monday = 0, Sunday = 6
    let startDow = firstDay.getDay() - 1;
    if (startDow < 0) startDow = 6;

    const weeks: (number | null)[][] = [];
    let week: (number | null)[] = [];
    for (let i = 0; i < startDow; i++) week.push(null);
    for (let d = 1; d <= lastDay; d++) {
      week.push(d);
      if (week.length === 7) {
        weeks.push(week);
        week = [];
      }
    }
    if (week.length > 0) {
      while (week.length < 7) week.push(null);
      weeks.push(week);
    }
    return weeks;
  }, [year, month]);

  // Summarize day status
  const getDaySummary = (dayStr: string): 'AVAILABLE' | 'BLOCKED' | 'MIXED' | 'TTL_PENDING' => {
    const slots = data?.days[dayStr];
    if (!slots || slots.length === 0) return 'BLOCKED';
    const hasAvailable = slots.some((s) => s.status === 'AVAILABLE');
    const hasBlocked = slots.some((s) => s.status !== 'AVAILABLE');
    if (hasAvailable && hasBlocked) return 'MIXED';
    if (hasAvailable) return 'AVAILABLE';
    const hasPending = slots.some((s) => s.status === 'TTL_PENDING');
    if (hasPending) return 'TTL_PENDING';
    return 'BLOCKED';
  };

  const daySummaryColors: Record<string, string> = {
    AVAILABLE: 'bg-green-100 border-green-300 text-green-800 hover:bg-green-200',
    BLOCKED: 'bg-gray-100 border-gray-300 text-gray-500',
    MIXED: 'bg-yellow-50 border-yellow-300 text-yellow-800 hover:bg-yellow-100',
    TTL_PENDING: 'bg-yellow-100 border-yellow-300 text-yellow-700 hover:bg-yellow-200',
  };

  const daySlots = expandedDay && data?.days[expandedDay] ? data.days[expandedDay] : [];

  return (
    <section aria-label="Calendario de disponibilidad" className="space-y-4">
      {/* Month navigation */}
      <div className="flex items-center justify-between">
        <button
          onClick={goPrev}
          className="p-2 rounded-lg hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
          aria-label="Mes anterior"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>
        <h3 className="text-lg font-semibold text-gray-900">
          {MONTH_NAMES[month - 1]} {year}
        </h3>
        <button
          onClick={goNext}
          className="p-2 rounded-lg hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
          aria-label="Mes siguiente"
        >
          <ChevronRight className="w-5 h-5" />
        </button>
      </div>

      {/* Legend */}
      <div className="flex gap-4 text-xs text-gray-600">
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded-sm bg-green-200 border border-green-400" />
          Disponible
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded-sm bg-yellow-200 border border-yellow-400" />
          En proceso
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded-sm bg-gray-200 border border-gray-400" />
          No disponible
        </span>
      </div>

      {/* Calendar grid */}
      {isLoading ? (
        <div className="h-64 flex items-center justify-center text-gray-400">
          Cargando disponibilidad...
        </div>
      ) : (
        <div className="border border-gray-200 rounded-xl overflow-hidden">
          {/* Day headers */}
          <div className="grid grid-cols-7 bg-gray-50 border-b border-gray-200">
            {DAY_NAMES.map((d) => (
              <div key={d} className="text-center text-xs font-medium text-gray-500 py-2">
                {d}
              </div>
            ))}
          </div>

          {/* Weeks */}
          {calendarWeeks.map((week, wi) => (
            <div key={wi} className="grid grid-cols-7 border-b border-gray-100 last:border-b-0">
              {week.map((day, di) => {
                if (day === null) {
                  return <div key={`empty-${di}`} className="p-2 min-h-[44px]" />;
                }
                const dayStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
                const summary = getDaySummary(dayStr);
                const isExpanded = expandedDay === dayStr;
                const isClickable = summary !== 'BLOCKED';

                return (
                  <button
                    key={day}
                    onClick={() => setExpandedDay(isExpanded ? null : dayStr)}
                    disabled={!isClickable && !isExpanded}
                    className={`p-2 min-h-[44px] text-sm font-medium border transition
                      focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-inset
                      ${isExpanded ? 'ring-2 ring-blue-500 bg-blue-50' : daySummaryColors[summary]}
                      ${isClickable ? 'cursor-pointer' : 'cursor-default'}
                    `}
                    aria-label={`${day} de ${MONTH_NAMES[month - 1]}: ${
                      summary === 'AVAILABLE' ? 'disponible' :
                      summary === 'MIXED' ? 'parcialmente disponible' :
                      summary === 'TTL_PENDING' ? 'en proceso' : 'no disponible'
                    }`}
                    aria-pressed={isExpanded}
                  >
                    {day}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      )}

      {/* Expanded day slots */}
      {expandedDay && daySlots.length > 0 && (
        <div
          className="bg-white border border-gray-200 rounded-xl p-4 space-y-2"
          role="region"
          aria-label={`Horarios del ${expandedDay}`}
        >
          <h4 className="text-sm font-semibold text-gray-700 mb-2">
            Horarios — {formatDateOnlyLocal(expandedDay)}
          </h4>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
            {daySlots.map((slot, i) => {
              const cfg = STATUS_COLORS[slot.status] || STATUS_COLORS.BLOCKED;
              const isAvailable = slot.status === 'AVAILABLE';
              return (
                <button
                  key={i}
                  onClick={() => isAvailable && onSlotSelect?.(slot)}
                  disabled={!isAvailable}
                  className={`px-3 py-2 rounded-lg border text-sm font-medium transition
                    ${cfg.bg} ${cfg.border}
                    ${isAvailable
                      ? 'cursor-pointer hover:ring-2 hover:ring-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-500'
                      : 'cursor-not-allowed opacity-70'}
                  `}
                  aria-label={`${formatTime(slot.hora_inicio)} a ${formatTime(slot.hora_fin)}: ${cfg.label}`}
                >
                  {formatTime(slot.hora_inicio)} – {formatTime(slot.hora_fin)}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
