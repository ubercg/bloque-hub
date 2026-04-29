/**
 * Cálculos y formato para la pantalla de confirmación de reserva (cotización).
 */

import { parseDateOnlyAsLocal } from '@/lib/dateUtils';

import type { CatalogPrices } from './catalog-pricing';
import { groupCartItemsBySpaceForReservationPeriod, type EventCartItem } from '../store/event-cart.store';

function timeToMinutes(t: string): number {
  const parts = t.split(':').map((x) => parseInt(x, 10));
  const h = parts[0] ?? 0;
  const m = parts[1] ?? 0;
  return h * 60 + m;
}

interface MergedTimeBlock {
  fecha: string;
  horaInicio: string;
  horaFin: string;
  precioTotal: number;
}

/**
 * Une slots contiguos por fecha (misma fecha y start==end anterior) para
 * descomponer sobre bloques reales seleccionados por el usuario.
 */
function mergeContiguousBlocks(items: EventCartItem[]): MergedTimeBlock[] {
  const byDate = new Map<string, EventCartItem[]>();
  for (const it of items) {
    if (!byDate.has(it.fecha)) byDate.set(it.fecha, []);
    byDate.get(it.fecha)!.push(it);
  }

  const out: MergedTimeBlock[] = [];
  for (const [fecha, arr] of byDate.entries()) {
    arr.sort((a, b) => {
      const s = a.horaInicio.localeCompare(b.horaInicio);
      if (s !== 0) return s;
      return a.horaFin.localeCompare(b.horaFin);
    });

    let current: MergedTimeBlock | null = null;
    for (const it of arr) {
      if (!current) {
        current = {
          fecha,
          horaInicio: it.horaInicio,
          horaFin: it.horaFin,
          precioTotal: it.precio,
        };
        continue;
      }

      if (timeToMinutes(it.horaInicio) === timeToMinutes(current.horaFin)) {
        current.horaFin = it.horaFin;
        current.precioTotal += it.precio;
      } else {
        out.push(current);
        current = {
          fecha,
          horaInicio: it.horaInicio,
          horaFin: it.horaFin,
          precioTotal: it.precio,
        };
      }
    }
    if (current) out.push(current);
  }

  out.sort((a, b) => {
    const d = a.fecha.localeCompare(b.fecha);
    if (d !== 0) return d;
    return a.horaInicio.localeCompare(b.horaInicio);
  });
  return out;
}

/** Duración del slot en horas (decimal). */
export function slotDurationHours(horaInicio: string, horaFin: string): number {
  const a = timeToMinutes(horaInicio);
  const b = timeToMinutes(horaFin);
  const diff = b - a;
  if (diff <= 0) return 1;
  return diff / 60;
}

/** Etiqueta legible: "1 hora", "2 horas", "1 h 30 min". */
export function formatDurationLabel(hours: number): string {
  if (hours <= 0) return '—';
  const whole = Math.floor(hours);
  const frac = hours - whole;
  if (frac < 0.01) {
    return whole === 1 ? '1 hora' : `${whole} horas`;
  }
  const mins = Math.round(frac * 60);
  if (whole === 0) return `${mins} min`;
  return `${whole} h ${mins} min`;
}

export interface OrderTableRow {
  key: string;
  espacio: string;
  tiempoLabel: string;
  precioUnitario: number;
  cantidad: number;
  total: number;
}

export type PricingBySpaceId = Record<string, CatalogPrices>;

const EPS = 1e-6;

/** 1 mes de referencia (30 días × 24 h) — catálogo "por mes (hasta 11 meses)". */
const HOURS_PER_MONTH_PACKAGE = 30 * 24;
/** 1 semana = 5 días × 24 h — catálogo "por semana". */
const HOURS_PER_WEEK_PACKAGE = 5 * 24;
const MAX_MONTH_PACKAGES = 11;

export interface PackageSegment {
  kind: string;
  label: string;
  qty: number;
  unitCatalog: number;
}

/**
 * Descompone horas totales en paquetes según docs/catalog_espacios.md:
 * mes (hasta 11), semana (5 días × 24 h), 12 h, 6 h, por hora (resto &lt; 6 h).
 */
export function decomposeHoursIntoPackages(totalHours: number, prices: CatalogPrices): PackageSegment[] {
  const out: PackageSegment[] = [];
  let h = Math.max(0, totalHours);

  if (prices.mes > 0) {
    const n = Math.min(Math.floor(h / HOURS_PER_MONTH_PACKAGE + EPS), MAX_MONTH_PACKAGES);
    if (n > 0) {
      out.push({ kind: 'mes', label: 'mes', qty: n, unitCatalog: prices.mes });
      h -= n * HOURS_PER_MONTH_PACKAGE;
    }
  }

  if (prices.semana > 0) {
    const n = Math.floor(h / HOURS_PER_WEEK_PACKAGE + EPS);
    if (n > 0) {
      out.push({ kind: 'semana', label: 'semana (5 días)', qty: n, unitCatalog: prices.semana });
      h -= n * HOURS_PER_WEEK_PACKAGE;
    }
  }

  if (prices.doceHoras > 0) {
    const n12 = Math.floor(h / 12 + EPS);
    if (n12 > 0) {
      out.push({ kind: 'h12', label: '12 horas', qty: n12, unitCatalog: prices.doceHoras });
      h -= n12 * 12;
    }
  }

  if (prices.seisHoras > 0) {
    const n6 = Math.floor(h / 6 + EPS);
    if (n6 > 0) {
      out.push({ kind: 'h6', label: '6 horas', qty: n6, unitCatalog: prices.seisHoras });
      h -= n6 * 6;
    }
  }

  if (h > EPS && prices.porHora > 0) {
    out.push({ kind: 'hora', label: 'por hora', qty: h, unitCatalog: prices.porHora });
  }

  return out;
}

/**
 * Fallback cuando no hay match de catálogo:
 * descompone por reglas de tiempo (12h, 6h, resto por hora) sin depender de tarifas.
 */
function decomposeHoursByTimeOnly(totalHours: number): PackageSegment[] {
  const out: PackageSegment[] = [];
  let h = Math.max(0, totalHours);

  const n12 = Math.floor(h / 12 + EPS);
  if (n12 > 0) {
    out.push({ kind: 'h12', label: '12 horas', qty: n12, unitCatalog: 0 });
    h -= n12 * 12;
  }

  const n6 = Math.floor(h / 6 + EPS);
  if (n6 > 0) {
    out.push({ kind: 'h6', label: '6 horas', qty: n6, unitCatalog: 0 });
    h -= n6 * 6;
  }

  if (h > EPS) {
    out.push({ kind: 'hora', label: 'por hora', qty: h, unitCatalog: 0 });
  }
  return out;
}

/** Reparte `total` MXN proporcionalmente a pesos (evita centavos en suma). */
function allocateTotalsMXN(total: number, weights: number[]): number[] {
  const sumW = weights.reduce((a, b) => a + b, 0);
  if (weights.length === 0) return [];
  if (sumW <= 0) return weights.map(() => 0);
  const n = weights.length;
  const out: number[] = [];
  let acc = 0;
  for (let i = 0; i < n - 1; i++) {
    const t = Math.round((total * weights[i]) / sumW);
    out.push(t);
    acc += t;
  }
  out.push(total - acc);
  return out;
}

function getSegmentUnitPriceFromPricing(seg: PackageSegment, prices: CatalogPrices): number {
  if (seg.kind === 'mes') {
    if ((prices.mes ?? 0) > 0) return prices.mes;
    return Math.round((prices.porHora ?? 0) * HOURS_PER_MONTH_PACKAGE);
  }
  if (seg.kind === 'semana') {
    if ((prices.semana ?? 0) > 0) return prices.semana;
    return Math.round((prices.porHora ?? 0) * HOURS_PER_WEEK_PACKAGE);
  }
  if (seg.kind === 'h12') {
    if ((prices.doceHoras ?? 0) > 0) return prices.doceHoras;
    if ((prices.seisHoras ?? 0) > 0) return Math.round(prices.seisHoras * 2);
    return Math.round((prices.porHora ?? 0) * 12);
  }
  if (seg.kind === 'h6') {
    if ((prices.seisHoras ?? 0) > 0) return prices.seisHoras;
    return Math.round((prices.porHora ?? 0) * 6);
  }
  return prices.porHora ?? 0;
}

/**
 * Filas de precotización: agrupa por espacio en todo el periodo de la reservación
 * (fecha/hora inicio → fecha/hora fin), suma horas y precio, luego descompone en paquetes.
 */
export function buildOrderTableRows(items: EventCartItem[], pricingBySpaceId: PricingBySpaceId = {}): OrderTableRow[] {
  const out: OrderTableRow[] = [];
  const groups = groupCartItemsBySpaceForReservationPeriod(items);

  for (const g of groups) {
    const prices = pricingBySpaceId[g.spaceId] ?? null;
    const byTime = new Map<string, OrderTableRow>();
    const rowDates = new Map<string, Set<string>>();
    const mergedBlocks = mergeContiguousBlocks(g.items);

    for (const block of mergedBlocks) {
      const hours = slotDurationHours(block.horaInicio, block.horaFin);
      const totalPrecio = Math.round(block.precioTotal);

      let segments: PackageSegment[] = [];
      if (prices) {
        const hasPackagePrices = (prices.doceHoras ?? 0) > 0 || (prices.seisHoras ?? 0) > 0;
        segments = hasPackagePrices
          ? decomposeHoursIntoPackages(hours, prices)
          : decomposeHoursByTimeOnly(hours);
      } else {
        segments = decomposeHoursByTimeOnly(hours);
      }
      if (segments.length === 0) {
        segments = [{ kind: 'hora', label: 'por hora', qty: Math.max(hours, 1), unitCatalog: 1 }];
      }

      const segTotals = prices
        ? segments.map((seg) => {
            const unit = getSegmentUnitPriceFromPricing(seg, prices);
            return Math.round(unit * seg.qty);
          })
        : allocateTotalsMXN(totalPrecio, segments.map((s) => s.qty));

      segments.forEach((seg, idx) => {
        const segTotal = segTotals[idx] ?? 0;
        const tiempoLabel =
          seg.kind === 'mes'
            ? 'mes'
            : seg.kind === 'semana'
              ? 'semana (5 días)'
              : seg.kind === 'h12'
                ? '12 horas'
                : seg.kind === 'h6'
                  ? '6 horas'
                  : 'por hora';
        const qty =
          seg.kind === 'hora'
            ? Math.max(seg.qty, 0)
            : Math.max(seg.qty, 0);
        const roundedQty = Math.round(qty * 100) / 100;
        const unitPrice = prices
          ? Math.round(getSegmentUnitPriceFromPricing(seg, prices))
          : roundedQty > EPS
            ? Math.round(segTotal / roundedQty)
            : segTotal;
        // Regla híbrida:
        // - Paquetes (mes/semana/12h/6h): consolidar en todo el evento.
        // - por hora: mantener desglose por día.
        const aggregateAcrossEvent = seg.kind !== 'hora';
        const k = aggregateAcrossEvent
          ? `${g.spaceId}|${tiempoLabel}|${unitPrice}`
          : `${g.spaceId}|${block.fecha}|${tiempoLabel}|${unitPrice}`;
        const prev = byTime.get(k);
        if (!prev) {
          const espacioLabel = g.spaceName;
          byTime.set(k, {
            key: `${g.key}|${k}`,
            espacio: espacioLabel,
            tiempoLabel,
            precioUnitario: unitPrice,
            cantidad: roundedQty,
            total: segTotal,
          });
          rowDates.set(k, new Set([block.fecha]));
          return;
        }

        prev.cantidad = Math.round((prev.cantidad + roundedQty) * 100) / 100;
        prev.total += segTotal;
        if (prev.cantidad > EPS) {
          prev.precioUnitario = Math.round(prev.total / prev.cantidad);
        }
        if (!rowDates.has(k)) rowDates.set(k, new Set());
        rowDates.get(k)!.add(block.fecha);
      });
    }

    const rows = Array.from(byTime.entries()).map(([k, row]) => {
      const dates = [...(rowDates.get(k) ?? new Set<string>())].sort();
      if (dates.length > 0) {
        row.espacio = `${g.spaceName} (${formatFechasEventoSpanish(dates)})`;
      }
      const firstDate = dates[0] ?? '9999-12-31';
      return { row, firstDate };
    }).sort((a, b) => {
      const byDate = a.firstDate.localeCompare(b.firstDate);
      if (byDate !== 0) return byDate;
      const rank = (label: string) => {
        if (label === 'mes') return 0;
        if (label === 'semana (5 días)') return 1;
        if (label === '12 horas') return 2;
        if (label === '6 horas') return 3;
        return 4; // por hora
      };
      const byRank = rank(a.row.tiempoLabel) - rank(b.row.tiempoLabel);
      if (byRank !== 0) return byRank;
      return a.row.tiempoLabel.localeCompare(b.row.tiempoLabel, 'es');
    }).map((x) => x.row);
    out.push(...rows);
  }

  return out;
}

/** Fechas únicas del carrito ordenadas (YYYY-MM-DD). */
export function uniqueCartDatesSorted(items: EventCartItem[]): string[] {
  return [...new Set(items.map((i) => i.fecha))].sort();
}

/**
 * Suma de capacidades por espacio (una vez por spaceId; usa max(capacidad) por si hay varias líneas).
 */
export function sumDistinctSpaceCapacities(items: EventCartItem[]): number {
  const bySpace = new Map<string, number>();
  for (const it of items) {
    const cap = it.capacidad ?? 0;
    const prev = bySpace.get(it.spaceId) ?? 0;
    bySpace.set(it.spaceId, Math.max(prev, cap));
  }
  let sum = 0;
  for (const v of bySpace.values()) sum += v;
  return sum;
}

function formatTimeAmPm(isoTime: string): string {
  const [hh, mm] = isoTime.split(':').map((x) => parseInt(x, 10));
  const d = new Date();
  d.setHours(hh ?? 0, mm ?? 0, 0, 0);
  return d.toLocaleTimeString('es-MX', {
    timeZone: 'America/Mexico_City',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

/** Rango global: desde la hora de inicio mínima hasta la hora de fin máxima (carrito). */
export function formatHorarioEvento(items: EventCartItem[]): string {
  if (items.length === 0) return '—';
  let minS = Infinity;
  let maxE = -Infinity;
  for (const it of items) {
    minS = Math.min(minS, timeToMinutes(it.horaInicio));
    maxE = Math.max(maxE, timeToMinutes(it.horaFin));
  }
  const toStr = (m: number) => {
    const h = Math.floor(m / 60);
    const mi = m % 60;
    return `${String(h).padStart(2, '0')}:${String(mi).padStart(2, '0')}`;
  };
  return `${formatTimeAmPm(toStr(minS))} a ${formatTimeAmPm(toStr(maxE))}`;
}

function itemStartMs(it: EventCartItem): number {
  const d = parseDateOnlyAsLocal(it.fecha);
  const [hh, mm] = it.horaInicio.split(':').map((x) => parseInt(x, 10));
  d.setHours(hh ?? 0, mm ?? 0, 0, 0);
  return d.getTime();
}

function itemEndMs(it: EventCartItem): number {
  const d = parseDateOnlyAsLocal(it.fecha);
  const [hh, mm] = it.horaFin.split(':').map((x) => parseInt(x, 10));
  d.setHours(hh ?? 0, mm ?? 0, 0, 0);
  return d.getTime();
}

/**
 * Periodo continuo de la reservación: primer inicio (fecha+hora) → último fin (fecha+hora).
 * Alineado con un evento que cruza días (ej. 6 feb 8:00 → 7 feb 20:00).
 */
export function formatReservationPeriodBoundsEs(items: EventCartItem[]): string {
  if (items.length === 0) return '—';
  let minT = Infinity;
  let maxT = -Infinity;
  for (const it of items) {
    minT = Math.min(minT, itemStartMs(it));
    maxT = Math.max(maxT, itemEndMs(it));
  }
  const start = new Date(minT);
  const end = new Date(maxT);
  const dOpts: Intl.DateTimeFormatOptions = {
    timeZone: 'America/Mexico_City',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  };
  const tOpts: Intl.DateTimeFormatOptions = {
    timeZone: 'America/Mexico_City',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  };
  const a = `${start.toLocaleDateString('es-MX', dOpts)}, ${start.toLocaleTimeString('es-MX', tOpts)}`;
  const b = `${end.toLocaleDateString('es-MX', dOpts)}, ${end.toLocaleTimeString('es-MX', tOpts)}`;
  return `Del ${a} al ${b}`;
}

const MONTHS_ES = [
  'enero',
  'febrero',
  'marzo',
  'abril',
  'mayo',
  'junio',
  'julio',
  'agosto',
  'septiembre',
  'octubre',
  'noviembre',
  'diciembre',
];

/** "6 y 7 de febrero de 2026" o "15 de marzo de 2026". */
export function formatFechasEventoSpanish(datesIso: string[]): string {
  const sorted = [...new Set(datesIso)].filter(Boolean).sort();
  if (sorted.length === 0) return '—';
  if (sorted.length === 1) {
    const d = parseDateOnlyAsLocal(sorted[0]);
    return `${d.getDate()} de ${MONTHS_ES[d.getMonth()]} de ${d.getFullYear()}`;
  }
  const y0 = parseDateOnlyAsLocal(sorted[0]).getFullYear();
  const sameYear = sorted.every((iso) => parseDateOnlyAsLocal(iso).getFullYear() === y0);
  const m0 = parseDateOnlyAsLocal(sorted[0]).getMonth();
  const sameMonth = sorted.every((iso) => parseDateOnlyAsLocal(iso).getMonth() === m0);
  if (sameYear && sameMonth) {
    const month = MONTHS_ES[m0];
    const days = sorted.map((iso) => parseDateOnlyAsLocal(iso).getDate());
    if (days.length === 2) {
      return `${days[0]} y ${days[1]} de ${month} de ${y0}`;
    }
    const last = days[days.length - 1];
    const rest = days.slice(0, -1);
    return `${rest.join(', ')} y ${last} de ${month} de ${y0}`;
  }
  return sorted
    .map((iso) => {
      const d = parseDateOnlyAsLocal(iso);
      return `${d.getDate()} de ${MONTHS_ES[d.getMonth()]} de ${d.getFullYear()}`;
    })
    .join('; ');
}

/** Fecha de hoy en zona México como YYYY-MM-DD (para input date). */
export function todayIsoMexico(): string {
  const s = new Date().toLocaleDateString('en-CA', { timeZone: 'America/Mexico_City' });
  return s;
}
