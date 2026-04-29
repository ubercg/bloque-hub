'use client';

import { CatalogSearch } from './CatalogSearch';

interface CatalogHeroProps {
  searchValue: string;
  onSearchChange: (value: string) => void;
  searchPlaceholder?: string;
}

export function CatalogHero({
  searchValue,
  onSearchChange,
  searchPlaceholder,
}: CatalogHeroProps) {
  return (
    <section
      className="relative overflow-hidden bg-gradient-to-br from-[#1e3a8a] via-[#1e40af] to-[#0f172a] text-white"
      aria-labelledby="catalog-hero-heading"
    >
      {/* Bloques de color + brillo (marketplace vibrante, sin layout shift en hover) */}
      <div className="pointer-events-none absolute -right-20 -top-24 h-80 w-80 rounded-full bg-amber-400/30 blur-3xl motion-reduce:blur-none" aria-hidden />
      <div className="pointer-events-none absolute -bottom-24 -left-16 h-72 w-72 rounded-full bg-amber-500/20 blur-3xl motion-reduce:blur-none" aria-hidden />
      <div
        className="absolute inset-0 opacity-[0.06] bg-[linear-gradient(to_right,#fff_1px,transparent_1px),linear-gradient(to_bottom,#fff_1px,transparent_1px)] bg-[size:2.5rem_2.5rem]"
        aria-hidden
      />
      <div className="relative max-w-5xl mx-auto px-4 sm:px-6 py-14 sm:py-20">
        <div className="text-center max-w-3xl mx-auto mb-10">
          <p className="text-xs sm:text-sm font-semibold uppercase tracking-[0.2em] text-amber-200/90 mb-3 font-catalog-display">
            Catálogo de espacios
          </p>
          <h1
            id="catalog-hero-heading"
            className="font-catalog-display text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight text-white drop-shadow-sm"
          >
            Encuentra el espacio ideal
          </h1>
          <p className="mt-3 text-base sm:text-lg text-blue-100/95 max-w-2xl mx-auto leading-relaxed">
            Salas y espacios listos para reuniones, talleres y eventos. Filtrá por piso y reservá con
            confianza.
          </p>
        </div>
        <div className="max-w-2xl mx-auto">
          <CatalogSearch
            value={searchValue}
            onChange={onSearchChange}
            placeholder={searchPlaceholder}
            aria-label="Buscar espacios por nombre o descripción"
            className="shadow-xl shadow-black/20"
          />
          <p className="mt-3 text-center text-xs text-blue-200/80">
            Tip: probá el nombre del espacio o palabras de la descripción.
          </p>
        </div>
      </div>
    </section>
  );
}
