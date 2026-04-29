'use client';

/**
 * Página 403: acceso denegado (rol sin permiso para la ruta solicitada).
 */

import Link from 'next/link';

export default function ForbiddenPage() {
  return (
    <div className="max-w-md mx-auto py-12 text-center">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Acceso denegado</h1>
      <p className="text-gray-600 mb-6">
        No tienes permiso para acceder a esta sección del back-office.
      </p>
      <div className="flex flex-wrap justify-center gap-3">
        <Link
          href="/admin"
          className="px-4 py-2 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700"
        >
          Ir al inicio del admin
        </Link>
        <Link
          href="/login"
          className="px-4 py-2 rounded-lg border border-gray-300 text-gray-700 font-medium hover:bg-gray-50"
        >
          Iniciar sesión con otra cuenta
        </Link>
      </div>
    </div>
  );
}
