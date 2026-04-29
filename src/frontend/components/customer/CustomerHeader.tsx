'use client';

/**
 * Header público reactivo al estado de autenticación.
 * Sin JWT: "Iniciar sesión". Con JWT: "Mis Eventos", "Cerrar sesión".
 */

import { useState, useRef, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuthStore } from '@/features/auth';
import { LogIn, Calendar, LogOut, ChevronDown } from 'lucide-react';

export default function CustomerHeader() {
  const pathname = usePathname();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const syncFromCookie = useAuthStore((s) => s.syncFromCookie);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const [synced, setSynced] = useState(false);

  // Sincronizar con cookie al montar: si no hay cookie, limpiar store para mostrar "Iniciar sesión"
  useEffect(() => {
    syncFromCookie();
    setSynced(true);
  }, [syncFromCookie]);

  const showLogin = !synced || !isAuthenticated;

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, []);

  const handleLogout = () => {
    setOpen(false);
    logout();
    window.location.href = '/login';
  };

  return (
    <div className="sticky top-4 z-40 pt-4 px-4 sm:px-6" role="banner">
      <header className="max-w-6xl mx-auto rounded-xl bg-white/95 backdrop-blur border border-gray-200 shadow-lg">
        <div className="px-4 sm:px-6 h-14 flex items-center justify-between">
        <nav className="flex items-center gap-6" aria-label="Navegación principal">
          <Link
            href="/"
            className="font-bold text-[#0F172A] hover:text-[#1E3A8A] transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-[#3B82F6] focus:ring-offset-2 rounded cursor-pointer"
          >
            BLOQUE
          </Link>
          <Link
            href="/catalog"
            className={`text-sm font-medium min-h-[44px] inline-flex items-center transition-colors duration-200 cursor-pointer ${
              pathname?.startsWith('/catalog')
                ? 'text-[#1E3A8A]'
                : 'text-[#475569] hover:text-[#0F172A]'
            }`}
          >
            Catálogo
          </Link>
        </nav>

        <div className="flex items-center gap-2" ref={ref}>
          {showLogin ? (
            <Link
              href="/login"
              className="inline-flex items-center gap-2 min-h-[44px] px-4 py-2 rounded-lg bg-[#F97316] text-white text-sm font-medium hover:bg-[#EA580C] transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-[#F97316] focus:ring-offset-2 cursor-pointer"
              aria-label="Iniciar sesión"
            >
              <LogIn className="w-4 h-4" />
              Iniciar sesión
            </Link>
          ) : (
            <div className="relative">
              <button
                type="button"
                onClick={() => setOpen((o) => !o)}
                className="inline-flex items-center gap-2 min-h-[44px] px-3 py-2 rounded-lg text-[#475569] hover:bg-gray-100 transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-[#3B82F6] cursor-pointer"
                aria-expanded={open}
                aria-haspopup="true"
                aria-label="Menú de usuario"
              >
                <span className="text-sm font-medium truncate max-w-[120px] text-[#0F172A]">
                  {user?.full_name?.trim() || user?.email || 'Usuario'}
                </span>
                <ChevronDown className={`w-4 h-4 transition-transform duration-200 ${open ? 'rotate-180' : ''}`} />
              </button>
              {open && (
                <div
                  className="absolute right-0 mt-1 w-52 py-1 bg-white rounded-lg border border-gray-200 shadow-lg"
                  role="menu"
                >
                  <Link
                    href="/my-events"
                    className="flex items-center gap-2 px-4 py-2 text-sm text-[#475569] hover:bg-gray-50 transition-colors duration-200 cursor-pointer"
                    role="menuitem"
                    onClick={() => setOpen(false)}
                  >
                    <Calendar className="w-4 h-4" />
                    Mis Eventos
                  </Link>
                  <button
                    type="button"
                    className="flex w-full items-center gap-2 px-4 py-2 text-sm text-[#475569] hover:bg-gray-50 transition-colors duration-200 cursor-pointer"
                    role="menuitem"
                    onClick={handleLogout}
                  >
                    <LogOut className="w-4 h-4" />
                    Cerrar sesión
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      </header>
    </div>
  );
}
