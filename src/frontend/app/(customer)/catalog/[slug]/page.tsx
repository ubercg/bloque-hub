'use client';

/**
 * Ficha de espacio — hero, galería, descripción, Matterport, disponibilidad.
 */

import { useParams, useSearchParams } from 'next/navigation';
import useSWR from 'swr';
import Link from 'next/link';
import { toast } from 'sonner';
import { useAuthStore } from '@/features/auth';
import apiClient from '@/lib/http/apiClient';
import { useEventCartStore } from '@/features/booking';
import {
  resolveMediaUrl,
  AvailabilityCalendar,
  MatterportViewer,
  PromoGallery,
} from '@/features/catalog';
import {
  Users,
  DollarSign,
  MapPin,
  ArrowLeft,
  Calendar,
  ExternalLink,
  Loader2,
} from 'lucide-react';

interface Space {
  id: string;
  name: string;
  slug: string;
  piso?: number;
  capacidad_maxima: number;
  precio_por_hora: number;
  matterport_url?: string | null;
  promo_hero_url?: string | null;
  promo_gallery_urls?: string[] | null;
  descripcion?: string;
  amenidades?: string[];
}

const fetcher = (url: string) => apiClient.get(url).then((res) => res.data);

export default function SpaceDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const slug = typeof params.slug === 'string' ? params.slug : '';
  const addSpace = useEventCartStore((state) => state.addSpace);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const sedeParam = searchParams.get('sede');
  const tenantIdParam = searchParams.get('tenant_id');
  const catalogQuery = isAuthenticated
    ? ''
    : tenantIdParam
      ? `tenant_id=${encodeURIComponent(tenantIdParam)}`
      : sedeParam
        ? `sede=${encodeURIComponent(sedeParam)}`
        : '';
  const spacesKey = isAuthenticated
    ? '/spaces?t=user'
    : catalogQuery
      ? `/spaces?${catalogQuery}`
      : '/spaces';
  const { data: spaces, error, isLoading } = useSWR<Space[]>(spacesKey, fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 60000,
  });

  const space = spaces?.find((s) => s.slug === slug);

  const handleAddToCart = (slotFecha: string, slotInicio: string, slotFin: string) => {
    if (!space) return;
    const horaInicio = slotInicio.slice(0, 5);
    const horaFin = slotFin.slice(0, 5);
    const hours =
      (parseInt(horaFin.split(':')[0]) * 60 + parseInt(horaFin.split(':')[1]) -
        parseInt(horaInicio.split(':')[0]) * 60 -
        parseInt(horaInicio.split(':')[1])) /
      60;
    addSpace({
      spaceId: space.id,
      spaceName: space.name,
      fecha: slotFecha,
      horaInicio,
      horaFin,
      precio: space.precio_por_hora * Math.max(hours, 1),
      capacidad: space.capacidad_maxima,
    });
    toast.success('Añadido al carrito. Podés elegir más horarios.');
  };

  if (isLoading || !spaces) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[320px] px-4">
        <Loader2 className="w-10 h-10 animate-spin text-[#2563eb]" aria-hidden />
        <p className="mt-4 text-sm font-medium text-[#57534e]">Cargando ficha del espacio…</p>
      </div>
    );
  }

  if (error || !space) {
    return (
      <div className="p-8 max-w-xl mx-auto text-center">
        <h1 className="font-catalog-display text-2xl font-bold text-[#78350F] mb-2">
          Espacio no encontrado
        </h1>
        <p className="text-[#57534e] mb-8 leading-relaxed">
          No existe un espacio con el identificador solicitado o ya no está disponible.
        </p>
        <Link
          href="/catalog"
          className="inline-flex items-center gap-2 px-5 py-3 bg-[#2563eb] text-white font-semibold rounded-xl hover:bg-[#1d4ed8] transition-colors duration-200 cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#2563eb] focus:ring-offset-2"
        >
          <ArrowLeft className="w-4 h-4" />
          Volver al catálogo
        </Link>
      </div>
    );
  }

  const heroSrc = space.promo_hero_url ? resolveMediaUrl(space.promo_hero_url) : '';

  return (
    <div className="px-4 sm:px-6 py-6 md:py-10 max-w-6xl mx-auto w-full pb-16">
      <Link
        href={catalogQuery ? `/catalog?${catalogQuery}` : '/catalog'}
        className="inline-flex items-center gap-2 text-sm font-medium text-[#57534e] hover:text-[#2563eb] mb-8 transition-colors duration-200 cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#2563eb] rounded-lg px-1 -ml-1"
      >
        <ArrowLeft className="w-4 h-4 shrink-0" />
        Volver al catálogo
      </Link>

      {/* Hero */}
      <div className="relative rounded-3xl overflow-hidden min-h-[200px] md:min-h-[280px] mb-10 shadow-lg shadow-amber-900/10 border border-amber-100/80">
        <div className="absolute inset-0 bg-gradient-to-br from-[#1e3a8a] via-[#2563eb] to-[#78350f]" />
        {heroSrc ? (
          <img
            src={heroSrc}
            alt={`${space.name} — imagen principal`}
            className="absolute inset-0 w-full h-full object-cover"
          />
        ) : null}
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/25 to-black/30" />
        <div className="relative flex flex-col items-center justify-center text-center text-white px-4 py-12 md:py-16 min-h-[200px] md:min-h-[280px]">
          <MapPin className="w-9 h-9 md:w-11 md:h-11 mb-3 opacity-95" aria-hidden />
          <h1 className="font-catalog-display text-2xl md:text-4xl font-bold tracking-tight drop-shadow-md max-w-3xl">
            {space.name}
          </h1>
          <p className="text-base md:text-lg mt-2 text-white/90 font-medium">
            Piso {space.piso ?? '—'}
          </p>
        </div>
      </div>

      {space.promo_gallery_urls && space.promo_gallery_urls.length > 0 && (
        <PromoGallery
          headingId="gallery-heading"
          items={space.promo_gallery_urls.map((url, i) => ({
            src: resolveMediaUrl(url),
            alt: `${space.name} — imagen de galería ${i + 1}`,
          }))}
        />
      )}

      <div className="grid md:grid-cols-3 gap-8 lg:gap-10">
        <div className="md:col-span-2 space-y-10 min-w-0">
          {space.descripcion && (
            <section aria-labelledby="desc-heading">
              <h2 id="desc-heading" className="font-catalog-display text-lg font-semibold text-[#78350F] mb-3">
                Descripción
              </h2>
              <p className="text-[#57534e] leading-relaxed whitespace-pre-line">{space.descripcion}</p>
            </section>
          )}

          {space.matterport_url && (
            <section className="w-full min-w-0" aria-labelledby="tour-heading">
              <h2 id="tour-heading" className="font-catalog-display text-lg font-semibold text-[#78350F] mb-3">
                Tour virtual 360°
              </h2>
              <div className="rounded-2xl border border-amber-100 bg-white shadow-sm overflow-hidden min-h-[420px]">
                <div className="w-full h-[420px] min-h-[420px]">
                  <MatterportViewer
                    url={space.matterport_url}
                    title={`Tour virtual ${space.name}`}
                    lazy
                    className="h-full min-h-[420px]"
                  />
                </div>
              </div>
              <a
                href={space.matterport_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 mt-4 text-sm font-semibold text-[#2563eb] hover:text-[#1d4ed8] transition-colors duration-200 cursor-pointer"
              >
                <ExternalLink className="w-4 h-4 shrink-0" />
                Abrir en nueva pestaña
              </a>
            </section>
          )}

          <section aria-labelledby="avail-heading">
            <h2 id="avail-heading" className="font-catalog-display text-lg font-semibold text-[#78350F] mb-2">
              Disponibilidad
            </h2>
            <p className="text-sm text-[#57534e] mb-4 leading-relaxed">
              Elegí un día y un horario disponible (en verde) para agregar al carrito. Podés sumar varios
              horarios del mismo espacio.
            </p>
            <AvailabilityCalendar
              spaceId={space.id}
              sedeQuery={catalogQuery || undefined}
              onSlotSelect={
                isAuthenticated
                  ? (slot) => {
                      handleAddToCart(slot.fecha, slot.hora_inicio, slot.hora_fin);
                    }
                  : undefined
              }
            />
          </section>
        </div>

        <aside className="space-y-6 md:sticky md:top-28 self-start">
          <div className="bg-white rounded-2xl border border-amber-100 p-6 shadow-md shadow-amber-900/5">
            <h2 className="font-catalog-display text-lg font-semibold text-[#78350F] mb-4">
              Características
            </h2>
            <ul className="space-y-3">
              <li className="flex items-center gap-3 text-[#57534e]">
                <Users className="w-5 h-5 text-[#2563eb] shrink-0" aria-hidden />
                <span>{space.capacidad_maxima} personas</span>
              </li>
              <li className="flex items-center gap-3 text-[#57534e]">
                <DollarSign className="w-5 h-5 text-emerald-600 shrink-0" aria-hidden />
                <span className="font-semibold text-[#0f172a]">
                  ${space.precio_por_hora.toLocaleString('es-MX')} MXN / hora
                </span>
              </li>
            </ul>

            {space.amenidades && space.amenidades.length > 0 && (
              <>
                <h3 className="text-sm font-semibold text-[#78350F] mt-5 mb-2">Amenidades</h3>
                <div className="flex flex-wrap gap-2">
                  {space.amenidades.map((a, i) => (
                    <span
                      key={i}
                      className="text-xs font-medium bg-amber-50 text-[#78350F] border border-amber-100 px-3 py-1 rounded-full"
                    >
                      {a}
                    </span>
                  ))}
                </div>
              </>
            )}
          </div>

          <div className="space-y-3">
            {isAuthenticated ? (
              <Link
                href={catalogQuery ? `/catalog?${catalogQuery}` : '/catalog'}
                className="block w-full text-center px-4 py-3.5 border-2 border-amber-200 text-[#78350F] font-semibold rounded-2xl hover:bg-amber-50 transition-colors duration-200 cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#2563eb] focus:ring-offset-2"
              >
                Ver más espacios
              </Link>
            ) : (
              <>
                <Link
                  href="/login"
                  className="w-full flex items-center justify-center gap-2 px-4 py-3.5 bg-[#2563eb] text-white font-semibold rounded-2xl hover:bg-[#1d4ed8] transition-colors duration-200 cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#2563eb] focus:ring-offset-2 shadow-md shadow-blue-900/10"
                >
                  <Calendar className="w-5 h-5 shrink-0" />
                  Iniciar sesión para reservar
                </Link>
                <Link
                  href={catalogQuery ? `/catalog?${catalogQuery}` : '/catalog'}
                  className="block w-full text-center px-4 py-3.5 border-2 border-amber-200 text-[#78350F] font-semibold rounded-2xl hover:bg-amber-50 transition-colors duration-200 cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#2563eb] focus:ring-offset-2"
                >
                  Ver más espacios
                </Link>
              </>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
