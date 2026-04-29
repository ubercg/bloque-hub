'use client';

/**
 * Catalog page — WeWork-style marketplace
 * Hero with search, filters bar (piso + sede), grid of SpaceCards.
 * Anonymous: GET /api/public/sedes; one sede → catalog; several → sede selector in filters.
 */

import { Suspense, useMemo, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import useSWR from 'swr';
import { useAuthStore } from '@/features/auth';
import apiClient from '@/lib/http/apiClient';
import {
  CatalogEmptyState,
  CatalogFilters,
  CatalogHero,
  SpaceCard,
  SpaceGrid,
} from '@/features/catalog';
import { SkeletonCardGrid } from '@/components/ui/Skeleton';

interface Sede {
  id: string;
  name: string;
  slug: string;
}

interface Space {
  id: string;
  name: string;
  slug: string;
  piso?: number;
  capacidad_maxima: number;
  precio_por_hora: number;
  matterport_url?: string | null;
  promo_hero_url?: string | null;
  descripcion?: string;
  amenidades?: string[];
}

const fetcher = (url: string) => apiClient.get(url).then((res) => res.data);

function parsePisoParam(value: string | null): number | null {
  if (value === null || value === '') return null;
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return Math.min(7, Math.max(0, Math.floor(n)));
}

function CatalogPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pisoFilter = useMemo(() => parsePisoParam(searchParams.get('piso')), [searchParams]);
  const [searchQuery, setSearchQuery] = useState('');

  const setPisoFilter = (value: number | null) => {
    const params = new URLSearchParams(searchParams.toString());
    if (value === null) params.delete('piso');
    else params.set('piso', String(value));
    const q = params.toString();
    router.replace(q ? `/catalog?${q}` : '/catalog');
  };

  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const sedeParam = searchParams.get('sede');
  const tenantIdParam = searchParams.get('tenant_id');
  const { data: sedes } = useSWR<Sede[]>(
    !isAuthenticated ? '/public/sedes' : null,
    fetcher,
    { revalidateOnFocus: false }
  );
  const selectedSede = useMemo(() => {
    if (isAuthenticated || !sedes?.length) return null;
    if (sedes.length === 1) return sedes[0];
    if (sedeParam) return sedes.find((s) => s.slug === sedeParam) ?? sedes[0];
    if (tenantIdParam) return sedes.find((s) => s.id === tenantIdParam) ?? sedes[0];
    return null;
  }, [isAuthenticated, sedes, sedeParam, tenantIdParam]);

  const spacesKey = isAuthenticated
    ? '/spaces?t=user'
    : selectedSede
      ? `/spaces?tenant_id=${selectedSede.id}`
      : null;
  const { data: spaces, error, isLoading } = useSWR<Space[]>(spacesKey, fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 60000,
  });

  const filteredSpaces = spaces?.filter((space) => {
    const matchesPiso = pisoFilter === null || (space.piso ?? null) === pisoFilter;
    const matchesSearch =
      searchQuery === '' ||
      space.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      space.descripcion?.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesPiso && matchesSearch;
  });

  const floorCounts = useMemo(() => {
    if (!spaces) return undefined;
    const map: Record<number, number> = {};
    for (const s of spaces) {
      const p = s.piso ?? 0;
      map[p] = (map[p] ?? 0) + 1;
    }
    return map;
  }, [spaces]);

  const showSedeSelector = !isAuthenticated && sedes && sedes.length > 1 && !selectedSede;
  const setSede = (sede: Sede) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set('sede', sede.slug);
    params.delete('tenant_id');
    router.replace(`/catalog?${params.toString()}`);
  };
  const clearSede = () => router.replace('/catalog');

  const handleClearFilters = () => {
    setPisoFilter(null);
    setSearchQuery('');
  };

  const showLoading =
    isLoading || (!isAuthenticated && !selectedSede && sedes && sedes.length > 1);

  return (
    <>
      <CatalogHero
        searchValue={searchQuery}
        onSearchChange={setSearchQuery}
        searchPlaceholder="Buscar espacios por nombre o descripción..."
      />

      <CatalogFilters
        pisoFilter={pisoFilter}
        onPisoChange={setPisoFilter}
        floorCounts={floorCounts}
        showSedeSelector={showSedeSelector}
        sedes={sedes}
        selectedSede={selectedSede}
        onSedeChange={setSede}
        onClearSede={clearSede}
        isAuthenticated={isAuthenticated}
      />

      <main
        id="main-content"
        className="max-w-6xl mx-auto px-4 sm:px-6 py-8 sm:py-10"
        role="main"
        aria-label="Catálogo de espacios"
        tabIndex={-1}
      >
        {showLoading && <SkeletonCardGrid count={6} />}

        {!isAuthenticated && sedes && sedes.length === 0 && (
          <div className="rounded-2xl border border-amber-100 bg-white/90 p-10 text-center shadow-sm">
            <p className="text-[#57534e] leading-relaxed">
              No hay sedes disponibles en este momento.
            </p>
          </div>
        )}

        {error && (
          <div className="rounded-2xl border border-red-200/80 bg-white p-8 text-center shadow-sm">
            <p className="text-red-800 font-medium">
              Error al cargar los espacios. Por favor intentá de nuevo.
            </p>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="mt-5 px-5 py-2.5 rounded-xl bg-red-600 text-white font-semibold hover:bg-red-700 transition-colors duration-200 cursor-pointer focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
            >
              Reintentar
            </button>
          </div>
        )}

        {!showLoading && !error && (isAuthenticated || selectedSede) && (
          <>
            {filteredSpaces && filteredSpaces.length > 0 ? (
              <SpaceGrid key={pisoFilter ?? 'all'}>
                {filteredSpaces.map((space) => (
                  <SpaceCard
                    key={space.id}
                    space={space}
                    showLoginCta={!isAuthenticated}
                    detailQuery={
                      !isAuthenticated && selectedSede
                        ? `sede=${encodeURIComponent(selectedSede.slug)}`
                        : undefined
                    }
                  />
                ))}
              </SpaceGrid>
            ) : (
              <CatalogEmptyState onClearFilters={handleClearFilters} />
            )}
          </>
        )}

        {!showLoading && filteredSpaces && filteredSpaces.length > 0 && (
          <div className="mt-10 text-center text-sm text-[#57534e]">
            Mostrando{' '}
            <span className="font-semibold text-[#78350F]">{filteredSpaces.length}</span> de{' '}
            {spaces?.length ?? 0} espacios disponibles
          </div>
        )}
      </main>
    </>
  );
}

export default function CatalogPage() {
  return (
    <Suspense
      fallback={
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
          <div className="h-44 rounded-2xl bg-gradient-to-br from-slate-200 to-slate-100 animate-pulse mb-6" />
          <div className="h-20 rounded-2xl bg-slate-100 border border-slate-200/80 animate-pulse mb-8" />
          <SkeletonCardGrid count={6} />
        </div>
      }
    >
      <CatalogPageContent />
    </Suspense>
  );
}
