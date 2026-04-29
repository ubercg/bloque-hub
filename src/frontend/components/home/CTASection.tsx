'use client';

import Link from 'next/link';
import { ArrowRight } from 'lucide-react';

export function CTASection() {
  return (
    <section className="py-16 sm:py-20 bg-white border-t border-gray-200" aria-labelledby="cta-heading">
      <div className="max-w-3xl mx-auto px-6 text-center">
        <h2 id="cta-heading" className="text-2xl sm:text-3xl font-bold text-[#0F172A] mb-4">
          Encuentra el espacio ideal
        </h2>
        <p className="text-[#475569] mb-8 text-lg">
          Explora el catálogo por piso, revisa capacidad y precios, y reserva en minutos.
        </p>
        <Link
          href="/catalog"
          className="inline-flex items-center justify-center gap-2 px-8 py-4 bg-[#F97316] text-white font-semibold rounded-xl hover:bg-[#EA580C] transition-colors duration-200 shadow-md hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-[#F97316] focus:ring-offset-2 cursor-pointer"
        >
          Ir al catálogo de espacios
          <ArrowRight className="w-5 h-5" aria-hidden />
        </Link>
      </div>
    </section>
  );
}
