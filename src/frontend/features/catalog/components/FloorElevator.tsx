'use client';

/**
 * El Elevador - Selector visual de piso para el catálogo
 * Navegación vertical por pisos con transiciones suaves
 */

import { Building2 } from 'lucide-react';

const FLOORS = [0, 1, 2, 3, 4, 5, 6, 7] as const;

interface FloorElevatorProps {
  value: number | null;
  onChange: (piso: number | null) => void;
  /** Cantidad de espacios por piso (opcional, para mostrar en el botón) */
  counts?: Record<number, number>;
  id?: string;
}

export function FloorElevator({ value, onChange, counts, id = 'floor-elevator' }: FloorElevatorProps) {
  const hasSelection = value !== null;

  return (
    <div
      className="flex flex-row sm:flex-col items-center gap-1 rounded-xl border border-gray-200 bg-white p-2 shadow-sm transition-shadow hover:shadow-md"
      role="group"
      aria-labelledby={`${id}-label`}
    >
      <span id={`${id}-label`} className="sr-only">
        Seleccionar piso
      </span>
      <div className="flex items-center gap-1 text-gray-500 order-last sm:order-none sm:mb-1 ml-2 sm:ml-0" aria-hidden>
        <Building2 className="w-4 h-4" />
        <span className="text-xs font-medium hidden sm:inline">Piso</span>
      </div>

      {/* Botón "Todos" */}
      <button
        type="button"
        onClick={() => onChange(null)}
        className={`
          w-10 sm:w-10 h-9 sm:h-8 rounded-lg text-xs font-medium transition-all duration-200 flex-shrink-0
          focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1
          ${!hasSelection ? 'bg-blue-600 text-white shadow' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}
        `}
        aria-pressed={!hasSelection}
        aria-label="Todos los pisos"
      >
        Todos
      </button>

      {/* Lista de pisos: horizontal en móvil, vertical en sm+ */}
      <div className="flex flex-row sm:flex-col gap-0.5 sm:mt-1">
        {FLOORS.map((piso) => {
          const isActive = value === piso;
          const count = counts?.[piso] ?? null;
          return (
            <button
              key={piso}
              type="button"
              onClick={() => onChange(piso)}
              className={`
                w-9 h-9 sm:w-10 sm:h-9 rounded-lg text-sm font-semibold transition-all duration-200 flex items-center justify-center flex-shrink-0
                focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1
                ${isActive ? 'bg-blue-600 text-white shadow scale-105' : 'bg-gray-50 text-gray-700 hover:bg-gray-200'}
              `}
              aria-pressed={isActive}
              aria-label={`Piso ${piso}${count != null ? `, ${count} espacios` : ''}`}
              title={count != null ? `Piso ${piso}: ${count} espacios` : `Piso ${piso}`}
            >
              {piso}
            </button>
          );
        })}
      </div>
    </div>
  );
}
