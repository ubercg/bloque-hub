'use client';

/**
 * Portal del Cliente layout: Mis eventos, navegación y cierre de sesión.
 * Protected by middleware (auth required). Redirige a /login si no hay cookie (respaldo cliente).
 */

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Calendar, LayoutGrid, LogOut } from 'lucide-react';
import { hasAuthCookie, useAuthStore } from '@/features/auth';

export default function PortalLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const logout = useAuthStore((s) => s.logout);
  const syncFromCookie = useAuthStore((s) => s.syncFromCookie);
  const [allowed, setAllowed] = useState<boolean | null>(null);

  useEffect(() => {
    syncFromCookie();
    if (!hasAuthCookie()) {
      const loginUrl = `/login?redirect=${encodeURIComponent(pathname || '/my-events')}`;
      router.replace(loginUrl);
      return;
    }
    setAllowed(true);
  }, [pathname, router, syncFromCookie]);

  if (allowed !== true) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-500">Redirigiendo a inicio de sesión...</p>
      </div>
    );
  }

  const handleLogout = () => {
    logout();
    window.location.href = '/login';
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 py-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <Link
            href="/my-events"
            className="font-bold text-gray-900 text-lg sm:text-base min-h-[44px] flex items-center"
          >
            BLOQUE — Mi portal
          </Link>
          <nav className="flex flex-wrap items-center gap-2 sm:gap-4" role="navigation" aria-label="Portal">
            <Link
              href="/my-events"
              className={`flex items-center gap-2 px-4 py-3 min-h-[44px] rounded-lg text-sm font-medium touch-manipulation ${
                pathname?.startsWith('/my-events')
                  ? 'bg-blue-100 text-blue-800'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              <Calendar className="w-4 h-4 flex-shrink-0" />
              <span>Mis eventos</span>
            </Link>
            <Link
              href="/catalog"
              className="flex items-center gap-2 px-4 py-3 min-h-[44px] rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-100 touch-manipulation"
            >
              <LayoutGrid className="w-4 h-4 flex-shrink-0" />
              <span>Catálogo</span>
            </Link>
            <button
              type="button"
              onClick={handleLogout}
              className="flex items-center gap-2 px-4 py-3 min-h-[44px] rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-100 touch-manipulation"
              aria-label="Cerrar sesión"
            >
              <LogOut className="w-4 h-4 flex-shrink-0" />
              <span className="sm:inline">Cerrar sesión</span>
            </button>
          </nav>
        </div>
      </header>
      <main id="main-content" className="max-w-4xl mx-auto px-4 sm:px-6 py-4 sm:py-6" role="main" tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}
