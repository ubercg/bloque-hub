'use client';

import Link from 'next/link';

interface HeroSectionProps {
  showMyEvents: boolean;
}

export function HeroSection({ showMyEvents }: HeroSectionProps) {
  return (
    <section
      className="relative overflow-hidden bg-gradient-to-br from-[#1E3A8A] via-blue-800 to-slate-900 text-white"
      aria-labelledby="hero-heading"
    >
      {/* Subtle grid overlay for depth — no layout shift */}
      <div
        className="absolute inset-0 opacity-[0.07] bg-[linear-gradient(to_right,#fff_1px,transparent_1px),linear-gradient(to_bottom,#fff_1px,transparent_1px)] bg-[size:3rem_3rem]"
        aria-hidden
      />
      <div className="absolute inset-0 bg-gradient-to-t from-black/20 via-transparent to-transparent pointer-events-none" aria-hidden />

      <div className="relative max-w-5xl mx-auto px-6 py-20 sm:py-28 lg:py-32 text-center">
        <p className="text-blue-200 text-sm sm:text-base font-medium uppercase tracking-widest mb-4">
          Municipio de Querétaro
        </p>
        <h1 id="hero-heading" className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-bold tracking-tight mb-4">
          BLOQUE Hub
        </h1>
        <p className="text-xl sm:text-2xl text-blue-100 max-w-2xl mx-auto mb-10 font-light">
          Donde las ideas se transforman en realidad
        </p>
        <p className="text-base sm:text-lg text-blue-200/90 max-w-xl mx-auto mb-10">
          Reserva espacios oficiales para tu próximo evento. Simple, transparente y a tu medida.
        </p>

        <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
          <Link
            href="/catalog"
            className="w-full sm:w-auto inline-flex items-center justify-center px-8 py-4 bg-[#F97316] text-white font-semibold rounded-xl hover:bg-[#EA580C] transition-colors duration-200 shadow-lg hover:shadow-xl focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-blue-900 cursor-pointer"
            aria-label="Explorar catálogo de espacios"
          >
            Explorar catálogo
          </Link>
          {showMyEvents ? (
            <Link
              href="/my-events"
              className="w-full sm:w-auto inline-flex items-center justify-center px-8 py-4 border-2 border-white text-white font-semibold rounded-xl hover:bg-white/10 transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-blue-900 cursor-pointer"
              aria-label="Ver mis eventos"
            >
              Mis eventos
            </Link>
          ) : (
            <Link
              href="/login?redirect=/my-events"
              className="w-full sm:w-auto inline-flex items-center justify-center px-8 py-4 border-2 border-white text-white font-semibold rounded-xl hover:bg-white/10 transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-blue-900 cursor-pointer"
              aria-label="Iniciar sesión"
            >
              Iniciar sesión
            </Link>
          )}
        </div>
      </div>
    </section>
  );
}
