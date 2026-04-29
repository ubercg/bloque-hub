'use client';

/**
 * Muestra la fecha y hora actual (zona horaria Querétaro) en todo el sistema.
 * Ayuda a detectar desfases de fecha/hora entre cliente y servidor.
 * Actualización cada segundo.
 */

import { useState, useEffect } from 'react';

const TIMEZONE = 'America/Mexico_City';

function formatInTimezone(date: Date): string {
  return date.toLocaleString('es-MX', {
    timeZone: TIMEZONE,
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

export default function CurrentClock() {
  const [now, setNow] = useState<Date | null>(null);

  useEffect(() => {
    setNow(new Date());
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  if (now === null) return null;

  return (
    <div
      className="bg-gray-800 text-gray-200 text-xs px-3 py-1.5 flex items-center justify-center gap-2 font-mono"
      role="timer"
      aria-live="polite"
      aria-label={`Fecha y hora actual: ${formatInTimezone(now)}`}
    >
      <span className="text-gray-400" aria-hidden="true">
        Hora actual (Querétaro):
      </span>
      <span className="tabular-nums">{formatInTimezone(now)}</span>
    </div>
  );
}
