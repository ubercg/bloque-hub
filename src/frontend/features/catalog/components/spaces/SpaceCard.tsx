'use client';

/**
 * Tarjeta de espacio — marketplace: imagen hero, specs, CTA claro.
 */

import Link from 'next/link';
import { Users, DollarSign, ChevronRight } from 'lucide-react';
import { resolveMediaUrl } from '../../lib/resolveMediaUrl';

interface SpaceCardProps {
  space: {
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
  };
  showLoginCta?: boolean;
  detailQuery?: string;
}

function gradientIndex(str: string): number {
  let n = 0;
  for (let i = 0; i < str.length; i++) n = (n * 31 + str.charCodeAt(i)) >>> 0;
  return n % 4;
}

const GRADIENTS = [
  'from-[#1e3a8a] via-[#2563eb] to-[#1d4ed8]',
  'from-[#78350f] via-[#b45309] to-[#d97706]',
  'from-[#0f766e] via-[#0d9488] to-[#0f172a]',
  'from-[#5b21b6] via-[#7c3aed] to-[#1e3a8a]',
];

export default function SpaceCard({ space, showLoginCta = false, detailQuery }: SpaceCardProps) {
  const detailHref = detailQuery ? `/catalog/${space.slug}?${detailQuery}` : `/catalog/${space.slug}`;
  const idx = gradientIndex(space.id || space.name);
  const gradient = GRADIENTS[idx];
  const heroSrc = space.promo_hero_url ? resolveMediaUrl(space.promo_hero_url) : '';

  return (
    <article
      data-testid="space-card"
      className="group bg-white rounded-2xl overflow-hidden border border-amber-100/90 shadow-md shadow-amber-900/5 hover:shadow-xl hover:shadow-amber-900/10 hover:border-amber-200/80 transition-[box-shadow,border-color] duration-200"
    >
      <Link
        href={detailHref}
        className="group block cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[#2563eb] focus-visible:ring-offset-2 rounded-2xl"
      >
        <div className={`h-60 sm:h-64 relative bg-gradient-to-br ${gradient} overflow-hidden`}>
          {heroSrc ? (
            <img
              src={heroSrc}
              alt={`${space.name} — vista promocional`}
              className="absolute inset-0 w-full h-full object-cover transition-[filter] duration-200 group-hover:brightness-105 motion-reduce:group-hover:brightness-100"
            />
          ) : null}
          <div className="absolute inset-0 bg-gradient-to-t from-black/55 via-black/10 to-transparent" />
          <div className="absolute inset-0 flex items-end p-4">
            <span className="font-catalog-display text-white font-semibold text-lg leading-snug drop-shadow-md line-clamp-2">
              {space.name}
            </span>
          </div>
          <div className="absolute top-3 right-3 flex flex-col sm:flex-row gap-2 items-end">
            {space.piso != null && (
              <span className="bg-white/95 text-[#78350F] px-2.5 py-1 rounded-lg text-xs font-semibold shadow-sm">
                Piso {space.piso}
              </span>
            )}
            {space.matterport_url && (
              <span className="bg-[#2563eb] text-white px-2.5 py-1 rounded-lg text-xs font-semibold shadow-sm">
                Tour 360°
              </span>
            )}
          </div>
        </div>

        <div className="p-4 sm:p-5">
          <h3 className="font-catalog-display font-bold text-[#0F172A] text-lg mb-2 truncate" title={space.name}>
            {space.name}
          </h3>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-[#57534e] mb-3">
            <span className="flex items-center gap-1.5">
              <Users className="w-4 h-4 text-[#2563eb] shrink-0" aria-hidden />
              {space.capacidad_maxima} personas
            </span>
            <span className="flex items-center gap-1.5 font-semibold text-[#0F172A]">
              <DollarSign className="w-4 h-4 text-emerald-600 shrink-0" aria-hidden />
              ${space.precio_por_hora.toLocaleString('es-MX')} MXN / hr
            </span>
          </div>
          <span className="inline-flex items-center gap-1 text-[#2563eb] font-semibold text-sm group-hover:underline underline-offset-2">
            Ver detalles
            <ChevronRight className="w-4 h-4" aria-hidden />
          </span>
        </div>
      </Link>

      {showLoginCta && (
        <div className="px-4 sm:px-5 pb-4 pt-0">
          <Link
            href="/login"
            className="text-sm text-[#57534e] hover:text-[#2563eb] transition-colors duration-200 cursor-pointer font-medium"
          >
            Iniciar sesión para reservar
          </Link>
        </div>
      )}
    </article>
  );
}
