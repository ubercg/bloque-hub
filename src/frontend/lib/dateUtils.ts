/**
 * Utilidades de fecha para todo el sistema (portal, admin, booking).
 * Usa America/Mexico_City para evitar desfase de un día: las fechas YYYY-MM-DD
 * del API interpretadas como medianoche UTC se muestran como día anterior en México.
 */

const TIMEZONE = 'America/Mexico_City';

/**
 * Parsea una fecha solo-día (YYYY-MM-DD) como mediodía local para evitar desfase.
 * Usar este Date para formatear con toLocaleDateString (o formatDateOnlyLocal).
 */
export function parseDateOnlyAsLocal(isoDate: string): Date {
  if (!isoDate || !/^\d{4}-\d{2}-\d{2}$/.test(isoDate)) return new Date(isoDate);
  return new Date(isoDate + 'T12:00:00');
}

/**
 * Formatea una fecha solo-día (YYYY-MM-DD) en español sin desfase.
 * Evita new Date(isoDate) que interpreta como medianoche UTC.
 */
export function formatDateOnlyLocal(isoDate: string): string {
  if (!isoDate || !/^\d{4}-\d{2}-\d{2}$/.test(isoDate)) return isoDate;
  const d = parseDateOnlyAsLocal(isoDate);
  return d.toLocaleDateString('es-MX', {
    timeZone: TIMEZONE,
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

/**
 * Formatea YYYY-MM-DD con opciones cortas (ej. "lun, 15 mar").
 */
export function formatDateOnlyShort(
  isoDate: string,
  options: { weekday?: 'short' | 'long'; month?: 'short' | 'long' } = {}
): string {
  if (!isoDate || !/^\d{4}-\d{2}-\d{2}$/.test(isoDate)) return isoDate;
  const d = parseDateOnlyAsLocal(isoDate);
  return d.toLocaleDateString('es-MX', {
    timeZone: TIMEZONE,
    weekday: options.weekday ?? 'short',
    year: 'numeric',
    month: options.month ?? 'short',
    day: 'numeric',
  });
}

/**
 * Lista de fechas YYYY-MM-DD entre from y to (inclusive).
 * Iteración sin timezone para rangos en dashboards.
 */
export function getDateRangeInclusive(from: string, to: string): string[] {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(from) || !/^\d{4}-\d{2}-\d{2}$/.test(to)) return [];
  const [y1, m1, d1] = from.split('-').map(Number);
  const [y2, m2, d2] = to.split('-').map(Number);
  const out: string[] = [];
  let y = y1;
  let m = m1;
  let d = d1;
  const pad = (n: number) => String(n).padStart(2, '0');
  while (y < y2 || (y === y2 && m < m2) || (y === y2 && m === m2 && d <= d2)) {
    out.push(`${y}-${pad(m)}-${pad(d)}`);
    d++;
    const lastDay = new Date(y, m, 0).getDate();
    if (d > lastDay) {
      d = 1;
      m++;
    }
    if (m > 12) {
      m = 1;
      y++;
    }
  }
  return out;
}

/**
 * Fecha de hoy en America/Mexico_City como YYYY-MM-DD.
 * Para valores por defecto y validaciones en el frontend.
 */
export function todayMexico(): string {
  const now = new Date();
  return now.toLocaleDateString('en-CA', { timeZone: TIMEZONE }); // en-CA => YYYY-MM-DD
}

/**
 * Primer y último día del mes actual en Mexico como YYYY-MM-DD.
 */
export function monthRangeMexico(): { from: string; to: string } {
  const now = new Date();
  const y = now.toLocaleString('en-CA', { timeZone: TIMEZONE, year: 'numeric' });
  const m = now.toLocaleString('en-CA', { timeZone: TIMEZONE, month: '2-digit' });
  const monthNum = Number(m); // 1-12
  const lastDay = new Date(Number(y), monthNum, 0).getDate(); // month 0-indexed
  return {
    from: `${y}-${m}-01`,
    to: `${y}-${m}-${String(lastDay).padStart(2, '0')}`,
  };
}
