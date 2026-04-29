'use client';

/**
 * Barra superior del portal admin: nombre del usuario, rol y cierre de sesión.
 */

import { LogOut } from 'lucide-react';

import { useAuthStore } from '../store/auth.store';

const ROLE_LABELS: Record<string, string> = {
  COMMERCIAL: 'Comercial',
  OPERATIONS: 'Operaciones',
  FINANCE: 'Finanzas',
  SUPERADMIN: 'SuperAdmin',
  CUSTOMER: 'Cliente',
};

export default function AdminHeader() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  const handleLogout = () => {
    logout();
    window.location.href = '/login';
  };

  const displayName = user?.full_name?.trim() || user?.email || 'Usuario';
  const roleLabel = user?.role ? ROLE_LABELS[user.role] || user.role : '—';

  return (
    <header
      className="shrink-0 h-14 px-4 flex items-center justify-between bg-white border-b border-gray-200"
      role="banner"
    >
      <div className="flex items-center gap-3 text-sm text-gray-700">
        <span className="font-medium text-gray-900" aria-label="Usuario actual">
          {displayName}
        </span>
        <span className="text-gray-500" aria-label="Rol">
          | {roleLabel}
        </span>
      </div>
      <button
        type="button"
        onClick={handleLogout}
        className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 min-h-[44px]"
        aria-label="Cerrar sesión"
      >
        <LogOut className="w-4 h-4 flex-shrink-0" />
        Cerrar sesión
      </button>
    </header>
  );
}
