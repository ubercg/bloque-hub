'use client';

/**
 * Dashboard de bienvenida del back-office con accesos rápidos por rol.
 * FINANCE: Conciliación SPEI, Monitor CFDI; OPERATIONS: Checklists del día; COMMERCIAL: CRM; SUPERADMIN: todos.
 */

import Link from 'next/link';
import { getModulesForRole, useAuthStore } from '@/features/auth';
import { Wallet, Calendar, Users, Settings, Building2, BadgeDollarSign, TicketPercent } from 'lucide-react';

interface QuickCard {
  href: string;
  label: string;
  description: string;
  icon: React.ElementType;
  modules: readonly string[];
}

const QUICK_CARDS: QuickCard[] = [
  {
    href: '/admin/crm',
    label: 'CRM',
    description: 'Leads, cotizaciones y propuestas',
    icon: Users,
    modules: ['crm'],
  },
  {
    href: '/admin/operations',
    label: 'Control Center',
    description: 'Timeline y Readiness',
    icon: Calendar,
    modules: ['operations'],
  },
  {
    href: '/admin/finance',
    label: 'Finanzas',
    description: 'Conciliación SPEI, CFDIs y créditos',
    icon: Wallet,
    modules: ['finance'],
  },
  {
    href: '/admin/occupancy',
    label: 'Ocupación',
    description: 'Estado de slots y eventos del edificio',
    icon: Building2,
    modules: ['occupancy'],
  },
  {
    href: '/admin/pricing',
    label: 'Cuotas',
    description: 'Configurar tarifas UMA y MXN por espacio',
    icon: BadgeDollarSign,
    modules: ['pricing'],
  },
  {
    href: '/admin/discounts',
    label: 'Descuentos',
    description: 'Gestión y auditoría de códigos promocionales',
    icon: TicketPercent,
    modules: ['discounts'],
  },
  {
    href: '/admin/settings',
    label: 'Ajustes',
    description: 'Tenants y usuarios',
    icon: Settings,
    modules: ['settings'],
  },
];

export default function AdminDashboardPage() {
  const role = useAuthStore((s) => s.user?.role);
  const allowedModules = getModulesForRole(role);

  const visibleCards = QUICK_CARDS.filter((card) =>
    card.modules.some((m) => allowedModules.includes(m))
  );

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-gray-900">Bienvenido al Hub Admin</h1>
      <p className="text-gray-600 text-sm">
        Selecciona un acceso rápido según tu rol.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {visibleCards.map(({ href, label, description, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className="flex flex-col p-4 rounded-xl border border-gray-200 bg-white hover:border-blue-300 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all min-h-[120px]"
          >
            <Icon className="w-8 h-8 text-blue-600 mb-2" aria-hidden />
            <h2 className="font-semibold text-gray-900">{label}</h2>
            <p className="text-sm text-gray-500 mt-1">{description}</p>
          </Link>
        ))}
      </div>
      {visibleCards.length === 0 && (
        <p className="text-gray-500 text-sm">No tienes módulos asignados. Contacta al administrador.</p>
      )}
    </div>
  );
}
