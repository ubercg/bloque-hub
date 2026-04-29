'use client';

import { useCallback, useEffect, useId, useState } from 'react';
import { ChevronLeft, ChevronRight, X } from 'lucide-react';

export interface PromoGalleryItem {
  src: string;
  alt: string;
}

interface PromoGalleryProps {
  items: PromoGalleryItem[];
  headingId?: string;
}

export function PromoGallery({ items, headingId = 'gallery-heading' }: PromoGalleryProps) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const titleId = useId();

  const close = useCallback(() => setOpenIndex(null), []);

  const goPrev = useCallback(() => {
    setOpenIndex((i) => {
      if (i === null || items.length < 2) return i;
      return i === 0 ? items.length - 1 : i - 1;
    });
  }, [items.length]);

  const goNext = useCallback(() => {
    setOpenIndex((i) => {
      if (i === null || items.length < 2) return i;
      return i === items.length - 1 ? 0 : i + 1;
    });
  }, [items.length]);

  useEffect(() => {
    if (openIndex === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
      if (e.key === 'ArrowLeft') goPrev();
      if (e.key === 'ArrowRight') goNext();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [openIndex, close, goPrev, goNext]);

  useEffect(() => {
    if (openIndex === null) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [openIndex]);

  if (items.length === 0) return null;

  return (
    <>
      <section className="mb-10" aria-labelledby={headingId}>
        <h2
          id={headingId}
          className="font-catalog-display text-lg font-semibold text-[#78350F] mb-2"
        >
          Galería
        </h2>
        <p id={`${headingId}-hint`} className="text-sm text-[#57534e] mb-4">
          Tocá o hacé clic en una imagen para verla en tamaño completo.
        </p>
        <div
          className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4"
          role="list"
          aria-describedby={`${headingId}-hint`}
        >
          {items.map((item, index) => (
            <button
              key={`${item.src}-${index}`}
              type="button"
              role="listitem"
              onClick={() => setOpenIndex(index)}
              className="relative aspect-video rounded-2xl overflow-hidden bg-gray-100 border border-gray-200/90 shadow-sm hover:shadow-md hover:border-[#2563eb]/40 transition-[box-shadow,border-color] duration-200 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-[#2563eb] focus-visible:ring-offset-2 p-0 text-left"
              aria-label={`Ampliar imagen ${index + 1} de ${items.length}`}
            >
              <img
                src={item.src}
                alt={item.alt}
                className="w-full h-full object-cover"
                loading="lazy"
                decoding="async"
              />
            </button>
          ))}
        </div>
      </section>

      {openIndex !== null && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6 bg-black/90"
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          onClick={close}
        >
          <p id={titleId} className="sr-only">
            Imagen ampliada, {openIndex + 1} de {items.length}. Escape para cerrar.
          </p>

          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              close();
            }}
            className="absolute top-3 right-3 sm:top-4 sm:right-4 z-[102] flex h-11 w-11 items-center justify-center rounded-full bg-white/10 text-white hover:bg-white/20 transition-colors duration-200 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-2 focus-visible:ring-offset-black/80"
            aria-label="Cerrar vista ampliada"
          >
            <X className="w-6 h-6" aria-hidden />
          </button>

          {items.length > 1 && (
            <>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  goPrev();
                }}
                className="absolute left-2 sm:left-4 top-1/2 -translate-y-1/2 z-[102] flex h-11 w-11 sm:h-12 sm:w-12 items-center justify-center rounded-full bg-white/10 text-white hover:bg-white/20 transition-colors duration-200 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-white"
                aria-label="Imagen anterior"
              >
                <ChevronLeft className="w-7 h-7 sm:w-8 sm:h-8" aria-hidden />
              </button>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  goNext();
                }}
                className="absolute right-2 sm:right-4 top-1/2 -translate-y-1/2 z-[102] flex h-11 w-11 sm:h-12 sm:w-12 items-center justify-center rounded-full bg-white/10 text-white hover:bg-white/20 transition-colors duration-200 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-white"
                aria-label="Imagen siguiente"
              >
                <ChevronRight className="w-7 h-7 sm:w-8 sm:h-8" aria-hidden />
              </button>
            </>
          )}

          <img
            src={items[openIndex].src}
            alt={items[openIndex].alt}
            className="relative z-[101] max-h-[min(92vh,100%)] max-w-full w-auto h-auto object-contain select-none"
            onClick={(e) => e.stopPropagation()}
            draggable={false}
          />

          {items.length > 1 && (
            <div
              className="absolute bottom-4 left-1/2 -translate-x-1/2 z-[102] rounded-full bg-black/50 px-3 py-1.5 text-sm text-white/95"
              aria-hidden
            >
              {openIndex + 1} / {items.length}
            </div>
          )}
        </div>
      )}
    </>
  );
}
