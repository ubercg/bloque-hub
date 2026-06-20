'use client';

/**
 * Hidrata el rol del usuario staff desde GET /me cuando hay token pero el store aún no tiene rol.
 * Usar en shell admin (no en layout crudo: vive en AdminShell container).
 */

import { useEffect } from 'react';

import apiClient from '@/lib/http/apiClient';

import { useAuthStore } from '../store/auth.store';

function getCookie(name: string) {
  if (typeof document === 'undefined') return null;
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop()?.split(';').shift();
  return null;
}

export function useStaffRoleHydration() {
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);
  const role = user?.role;

  useEffect(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') || getCookie('auth_token') : null;
    if (!token || role) return;
    apiClient
      .get<{ tenant_id: string; role: string | null; user_id: string }>('/me')
      .then(({ data }) => {
        if (data.role && user) {
          setUser({ ...user, role: data.role });
        }
      })
      .catch(() => {});
  }, [role, setUser, user]);
}
