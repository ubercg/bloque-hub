'use client';

import { Building2 } from 'lucide-react';

const FLOORS = [0, 1, 2, 3, 4, 5, 6, 7] as const;

export interface SedeOption {
  id: string;
  name: string;
  slug: string;
}

interface CatalogFiltersProps {
  pisoFilter: number | null;
  onPisoChange: (piso: number | null) => void;
  floorCounts?: Record<number, number>;
  /** Anonymous user, multiple sedes, none selected: show full sede selector */
  showSedeSelector?: boolean;
  sedes?: SedeOption[];
  selectedSede?: SedeOption | null;
  onSedeChange?: (sede: SedeOption) => void;
  onClearSede?: () => void;
  isAuthenticated?: boolean;
}

export function CatalogFilters({
  pisoFilter,
  onPisoChange,
  floorCounts,
  showSedeSelector,
  sedes = [],
  selectedSede,
  onSedeChange,
  onClearSede,
  isAuthenticated,
}: CatalogFiltersProps) {
  const hasPisoSelection = pisoFilter !== null;

  return (
    <div className="sticky top-24 z-20 border-b border-amber-200/80 bg-white/90 backdrop-blur-md shadow-sm md:rounded-b-2xl md:mx-4 md:max-w-6xl md:border md:border-amber-100/90 md:shadow-md lg:mx-auto">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4">
        {showSedeSelector && sedes.length > 1 && (
          <div className="mb-5">
            <h2 className="font-catalog-display text-sm font-semibold text-[#78350F] mb-3">
              Selecciona una sede
            </h2>
            <div className="flex flex-wrap gap-2">
              {sedes.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => onSedeChange?.(s)}
                  className="px-4 py-2.5 rounded-xl border-2 border-amber-100 bg-white text-[#57534e] font-medium hover:border-[#2563eb] hover:bg-blue-50/80 hover:text-[#1e3a8a] transition-colors duration-200 cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#2563eb] focus:ring-offset-2"
                >
                  {s.name}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center gap-2 flex-wrap" role="group" aria-label="Filtrar por piso">
            <span className="flex items-center gap-1.5 text-sm text-[#57534e] font-semibold">
              <Building2 className="w-4 h-4 text-[#d97706]" aria-hidden />
              Piso
            </span>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => onPisoChange(null)}
                className={`px-3 py-2 rounded-xl text-sm font-medium transition-colors duration-200 cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#2563eb] focus:ring-offset-2 ${
                  !hasPisoSelection
                    ? 'bg-[#2563eb] text-white shadow-sm'
                    : 'bg-amber-50 text-[#57534e] font-medium hover:bg-amber-100'
                }`}
                aria-pressed={!hasPisoSelection}
                aria-label="Todos los pisos"
              >
                Todos
              </button>
              {FLOORS.map((piso) => {
                const isActive = pisoFilter === piso;
                const count = floorCounts?.[piso];
                return (
                  <button
                    key={piso}
                    type="button"
                    onClick={() => onPisoChange(piso)}
                    className={`min-w-[2.5rem] px-2.5 py-2 rounded-xl text-sm font-medium transition-colors duration-200 cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#2563eb] focus:ring-offset-2 ${
                      isActive
                        ? 'bg-[#2563eb] text-white shadow-sm'
                        : 'bg-amber-50 text-[#57534e] hover:bg-amber-100'
                    }`}
                    aria-pressed={isActive}
                    aria-label={count != null ? `Piso ${piso}, ${count} espacios` : `Piso ${piso}`}
                    title={count != null ? `${count} espacios` : undefined}
                  >
                    {piso}
                    {count != null && (
                      <span className="ml-0.5 text-xs opacity-90">({count})</span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {!isAuthenticated && selectedSede && sedes.length > 1 && onClearSede && (
            <div className="flex items-center gap-2 flex-wrap sm:justify-end">
              <span className="text-sm text-[#57534e]">Sede</span>
              <span className="font-semibold text-[#78350F]">{selectedSede.name}</span>
              <button
                type="button"
                onClick={onClearSede}
                className="text-sm text-[#2563eb] hover:text-[#1d4ed8] font-semibold underline-offset-2 hover:underline transition-colors duration-200 cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#2563eb] rounded px-1"
              >
                Cambiar sede
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
