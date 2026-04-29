'use client';

import Link from 'next/link';
import { Search, CalendarPlus, CheckCircle } from 'lucide-react';

const steps = [
  {
    icon: Search,
    title: 'Explora',
    description: 'Revisa el catálogo por piso, capacidades y precios en tiempo real.',
    href: '/catalog',
  },
  {
    icon: CalendarPlus,
    title: 'Reserva',
    description: 'Elige fecha, horario y confirma. Pago por SPEI o cotización para eventos grandes.',
  },
  {
    icon: CheckCircle,
    title: 'Confirma',
    description: 'Recibe tu QR de acceso y gestiona evidencias desde el portal del cliente.',
  },
];

export function HowItWorksSection() {
  return (
    <section className="py-16 sm:py-20 bg-[#EFF6FF]" aria-labelledby="como-funciona-heading">
      <div className="max-w-5xl mx-auto px-6">
        <h2 id="como-funciona-heading" className="text-3xl sm:text-4xl font-bold text-[#0F172A] text-center mb-4">
          Cómo funciona
        </h2>
        <p className="text-[#475569] text-center max-w-xl mx-auto mb-12 text-lg">
          Tres pasos para tener tu espacio reservado en el recinto de innovación del Municipio.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {steps.map(({ icon: Icon, title, description, href }, i) => {
            const content = (
              <>
                <span className="flex-shrink-0 w-10 h-10 rounded-full bg-[#1E3A8A] text-white flex items-center justify-center text-sm font-bold">
                  {i + 1}
                </span>
                <div className="flex-shrink-0 w-12 h-12 rounded-lg bg-white text-[#1E3A8A] flex items-center justify-center shadow-sm border border-gray-200">
                  <Icon className="w-6 h-6" />
                </div>
                <h3 className="font-semibold text-[#0F172A] text-lg">{title}</h3>
                <p className="text-[#475569] text-sm leading-relaxed">{description}</p>
              </>
            );
            const baseClass =
              'flex flex-col items-center text-center gap-3 p-6 rounded-xl border border-gray-200 bg-white hover:border-blue-300 hover:shadow-md transition-colors duration-200';
            return href ? (
              <Link
                key={title}
                href={href}
                className={`${baseClass} cursor-pointer`}
                aria-label={`${title}: ${description}`}
              >
                {content}
              </Link>
            ) : (
              <div key={title} className={baseClass} role="article">
                {content}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
