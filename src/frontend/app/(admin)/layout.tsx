'use client';

/**
 * Layout admin: solo composición. Lógica de sesión en features/auth/containers/AdminShell.
 */

import { AdminShell } from '@/features/auth';

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <AdminShell>{children}</AdminShell>;
}
