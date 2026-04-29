'use client';

/**
 * Shell del back-office: sidebar, navegación por módulo y header.
 * Toda la lógica de hidratación de sesión vive aquí (no en layout.tsx).
 */

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  Users,
  Calendar,
  Wallet,
  Building2,
  BadgeDollarSign,
  TicketPercent,
  Settings,
  Images,
} from 'lucide-react';

import AdminHeader from '../components/AdminHeader';
import { getModulesForRole } from '../lib/permissions';
import { useAuthStore } from '../store/auth.store';
import { useStaffRoleHydration } from '../hooks/useStaffRoleHydration';

const MODULE_LINKS: { slug: string; href: string; label: string; icon: React.ElementType }[] = [
  { slug: 'crm', href: '/admin/crm', label: 'CRM', icon: Users },
  { slug: 'operations', href: '/admin/operations', label: 'Control Center', icon: Calendar },
  { slug: 'finance', href: '/admin/finance', label: 'Finanzas', icon: Wallet },
  { slug: 'occupancy', href: '/admin/occupancy', label: 'Ocupación', icon: Building2 },
  { slug: 'pricing', href: '/admin/pricing', label: 'Cuotas', icon: BadgeDollarSign },
  { slug: 'discounts', href: '/admin/discounts', label: 'Descuentos', icon: TicketPercent },
  { slug: 'settings', href: '/admin/settings', label: 'Ajustes', icon: Settings },
  { slug: 'spaces', href: '/admin/spaces', label: 'Espacios', icon: Images },
];

export function AdminShell({ children }: { children: React.ReactNode }) {
  useStaffRoleHydration();

  const pathname = usePathname();
  const role = useAuthStore((s) => s.user?.role);
  const allowedModules = getModulesForRole(role);
  const visibleLinks = MODULE_LINKS.filter((l) => allowedModules.includes(l.slug));

  return (
    <div className="min-h-screen bg-gray-50 flex">
      <aside className="w-56 bg-white border-r border-gray-200 flex flex-col shrink-0">
        <div className="p-4 border-b border-gray-200">
          <Link href="/admin/dashboard" className="flex items-center gap-2 font-bold text-gray-900">
            <LayoutDashboard className="w-6 h-6 text-blue-600" />
            BLOQUE Admin
          </Link>
        </div>
        <nav className="p-2 flex-1" role="navigation" aria-label="Administración">
          {visibleLinks.length === 0 ? (
            <p className="text-sm text-gray-500 px-3 py-2">Sin módulos asignados</p>
          ) : (
            <ul className="space-y-1">
              <li>
                <Link
                  href="/admin/dashboard"
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium min-h-[44px] ${
                    pathname === '/admin/dashboard'
                      ? 'bg-blue-100 text-blue-800'
                      : 'text-gray-700 hover:bg-gray-100'
                  }`}
                >
                  <LayoutDashboard className="w-4 h-4 flex-shrink-0" />
                  Dashboard
                </Link>
              </li>
              {visibleLinks.map(({ slug, href, label, icon: Icon }) => (
                <li key={slug}>
                  <Link
                    href={href}
                    className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium min-h-[44px] ${
                      pathname === href || pathname?.startsWith(href + '/')
                        ? 'bg-blue-100 text-blue-800'
                        : 'text-gray-700 hover:bg-gray-100'
                    }`}
                  >
                    <Icon className="w-4 h-4 flex-shrink-0" />
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </nav>
      </aside>
      <div className="flex-1 flex flex-col min-w-0">
        <AdminHeader />
        <main id="main-content" className="flex-1 overflow-auto p-6" role="main" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}
