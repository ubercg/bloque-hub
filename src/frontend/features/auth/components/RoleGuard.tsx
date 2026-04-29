'use client';

/**
 * RoleGuard: redirige a /admin/403 si el rol del usuario no está en allowedRoles.
 */

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

import { useAuthStore } from '../store/auth.store';

interface RoleGuardProps {
  allowedRoles: readonly string[];
  children: React.ReactNode;
}

export default function RoleGuard({ allowedRoles, children }: RoleGuardProps) {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const role = user?.role ?? null;

  useEffect(() => {
    if (role === null) {
      return;
    }
    const allowed = allowedRoles.includes(role);
    if (!allowed) {
      router.replace('/admin/403');
    }
  }, [role, allowedRoles, router]);

  if (role === null) {
    return (
      <div className="flex items-center justify-center min-h-[200px] text-gray-500">
        Verificando permisos...
      </div>
    );
  }

  if (!allowedRoles.includes(role)) {
    return null;
  }

  return <>{children}</>;
}
