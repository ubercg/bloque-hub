'use client';

/**
 * Booking Success Page — Post-reservation confirmation (FR-08)
 * Shows folio, total, TTL, and instructions: Pase de Caja in < 4h, SPEI when slip is sent.
 */

import { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { CheckCircle, FileText, Clock, CreditCard } from 'lucide-react';

function BookingSuccessContent() {
  const searchParams = useSearchParams();
  const id = searchParams.get('id');
  const total = searchParams.get('total');
  const count = searchParams.get('count');
  const ttl = searchParams.get('ttl');

  const ttlDate = ttl ? new Date(ttl) : null;
  const ttlFormatted =
    ttlDate && !Number.isNaN(ttlDate.getTime())
      ? ttlDate.toLocaleString('es-MX', {
          dateStyle: 'long',
          timeStyle: 'short',
          timeZone: 'America/Mexico_City',
        })
      : null;

  if (!id) {
    return (
      <div className="max-w-xl mx-auto p-8 text-center">
        <p className="text-gray-600 mb-4">No se encontró información de la reserva.</p>
        <Link
          href="/catalog"
          className="text-blue-600 hover:text-blue-700 font-medium"
        >
          Ir al catálogo
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto p-8">
      <div className="text-center mb-8">
        <CheckCircle className="w-16 h-16 text-green-600 mx-auto mb-4" />
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Reserva creada</h1>
        <p className="text-gray-600">
          Tu pre-reserva fue aceptada. Sigue los pasos siguientes para completar el pago.
        </p>
      </div>

      <div className="bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden">
        <div className="p-6 space-y-6">
          <div className="flex items-center gap-3">
            <FileText className="w-8 h-8 text-blue-600 flex-shrink-0" />
            <div>
              <div className="text-sm text-gray-500">Folio de reserva</div>
              <div className="font-mono font-bold text-lg text-gray-900 break-all">{id}</div>
            </div>
          </div>

          {total && (
            <div className="flex items-center gap-3">
              <CreditCard className="w-8 h-8 text-blue-600 flex-shrink-0" />
              <div>
                <div className="text-sm text-gray-500">Total a pagar</div>
                <div className="font-bold text-xl text-gray-900">
                  ${Number(total).toLocaleString('es-MX')} MXN
                </div>
              </div>
            </div>
          )}

          {ttlFormatted && (
            <div className="flex items-center gap-3">
              <Clock className="w-8 h-8 text-amber-600 flex-shrink-0" />
              <div>
                <div className="text-sm text-gray-500">Fecha límite de pago (TTL 24h)</div>
                <div className="font-medium text-gray-900">{ttlFormatted}</div>
              </div>
            </div>
          )}

          {count && Number(count) > 1 && (
            <p className="text-sm text-gray-600">
              Se crearon {count} reservas. Este folio corresponde a la primera; recibirás el Pase de
              Caja para cada una por correo.
            </p>
          )}
        </div>

        <div className="bg-blue-50 border-t border-blue-100 p-6">
          <h2 className="font-semibold text-gray-900 mb-2">Próximos pasos</h2>
          <ul className="text-sm text-gray-700 space-y-2 list-disc list-inside">
            <li>
              Tu reserva está en estado <strong>Pre-reserva</strong>. Recibirás un correo en{' '}
              <strong>menos de 4 horas hábiles</strong> con tu Pase de Caja oficial.
            </li>
            <li>
              El Pase de Caja incluirá la <strong>CLABE interbancaria</strong> y la{' '}
              <strong>referencia SPEI</strong> para realizar la transferencia.
            </li>
            <li>
              Una vez que recibas el Pase de Caja, podrás subir tu comprobante de pago desde{' '}
              <strong>el detalle de tu reserva</strong>.
            </li>
          </ul>
        </div>
      </div>

      <div className="mt-8 flex flex-col sm:flex-row gap-4 justify-center">
        <Link
          href={`/my-events/${id}`}
          className="inline-flex items-center justify-center px-6 py-3 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 transition"
        >
          Ver mi reserva
        </Link>
        <Link
          href="/catalog"
          className="inline-flex items-center justify-center px-6 py-3 border border-gray-300 text-gray-700 font-medium rounded-lg hover:bg-gray-50 transition"
        >
          Volver al catálogo
        </Link>
      </div>
    </div>
  );
}

export default function BookingSuccessPage() {
  return (
    <Suspense
      fallback={
        <div className="max-w-2xl mx-auto p-8 text-center text-gray-500">
          Cargando...
        </div>
      }
    >
      <BookingSuccessContent />
    </Suspense>
  );
}
