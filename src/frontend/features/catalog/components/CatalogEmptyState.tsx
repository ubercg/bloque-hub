'use client';

import { Search } from 'lucide-react';

interface CatalogEmptyStateProps {
  onClearFilters: () => void;
}

export function CatalogEmptyState({ onClearFilters }: CatalogEmptyStateProps) {
  return (
    <div
      className="flex flex-col items-center justify-center py-16 px-4 text-center rounded-2xl border border-amber-100 bg-white/80 shadow-sm"
      role="status"
      aria-live="polite"
    >
      <div className="w-16 h-16 rounded-2xl bg-amber-50 border border-amber-100 flex items-center justify-center mb-5">
        <Search className="w-8 h-8 text-amber-700/70" aria-hidden />
      </div>
      <h2 className="font-catalog-display text-xl font-semibold text-[#78350F] mb-2">
        No hay resultados
      </h2>
      <p className="text-[#57534e] max-w-sm mb-8 leading-relaxed">
        No encontramos espacios con los filtros actuales. Probá otro piso o ajustá la búsqueda.
      </p>
      <button
        type="button"
        onClick={onClearFilters}
        className="px-6 py-3 rounded-xl bg-[#2563eb] text-white font-semibold hover:bg-[#1d4ed8] transition-colors duration-200 cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#2563eb] focus:ring-offset-2 focus:ring-offset-white"
      >
        Limpiar filtros
      </button>
    </div>
  );
}
