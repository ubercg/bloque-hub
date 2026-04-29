'use client';

import { MapPin, CalendarCheck, FileCheck, Shield } from 'lucide-react';

const items = [
  {
    icon: MapPin,
    title: 'Espacios oficiales',
    description: 'Salas, auditorios y áreas del Municipio de Querétaro disponibles por hora o por evento.',
  },
  {
    icon: CalendarCheck,
    title: 'Reserva en línea',
    description: 'Consulta disponibilidad, elige fecha y horario, y confirma tu reserva con pocos pasos.',
  },
  {
    icon: FileCheck,
    title: 'Pase de caja y comprobantes',
    description: 'Proceso claro de pago y subida de comprobantes; seguimiento del estado de tu reserva.',
  },
  {
    icon: Shield,
    title: 'Evidencias y cumplimiento',
    description: 'Buzón de evidencias integrado para entregar documentación requerida por operaciones.',
  },
];

export function ValueSection() {
  return (
    <section className="py-16 sm:py-24 bg-white" aria-labelledby="valor-heading">
      <div className="max-w-5xl mx-auto px-6">
        <h2 id="valor-heading" className="text-3xl sm:text-4xl font-bold text-[#0F172A] text-center mb-4">
          ¿Por qué BLOQUE?
        </h2>
        <p className="text-[#475569] text-center max-w-2xl mx-auto mb-12 text-lg">
          Una sola plataforma para descubrir espacios, reservar y gestionar tus eventos con el Municipio.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {items.map(({ icon: Icon, title, description }) => (
            <div
              key={title}
              className="flex gap-4 p-6 rounded-xl border border-gray-200 bg-[#EFF6FF]/30 hover:border-blue-300 hover:shadow-md transition-colors duration-200 cursor-default"
              role="article"
            >
              <div
                className="flex-shrink-0 w-12 h-12 rounded-lg bg-blue-100 text-[#1E3A8A] flex items-center justify-center"
                aria-hidden
              >
                <Icon className="w-6 h-6" />
              </div>
              <div>
                <h3 className="font-semibold text-[#0F172A] mb-1">{title}</h3>
                <p className="text-[#475569] text-sm leading-relaxed">{description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
