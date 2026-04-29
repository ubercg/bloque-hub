'use client';

/**
 * Redirige /admin al dashboard de bienvenida (accesos rápidos por rol).
 * Si el usuario no tiene módulos asignados, redirige a 403.
 */

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { getModulesForRole, useAuthStore } from '@/features/auth';

export default function AdminIndexPage() {
  const router = useRouter();
  const role = useAuthStore((s) => s.user?.role);
  const modules = getModulesForRole(role);

  useEffect(() => {
    if (role === undefined) return;
    if (modules.length > 0) {
      router.replace('/admin/dashboard');
    } else {
      router.replace('/admin/403');
    }
  }, [role, modules, router]);

  return (
    <div className="flex items-center justify-center min-h-[200px] text-gray-500">
      Redirigiendo...
    </div>
  );
}
