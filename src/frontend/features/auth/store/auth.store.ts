/**
 * Authentication state management with Zustand
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import type { AuthUser } from '../types';

export function hasAuthCookie(): boolean {
  if (typeof window === 'undefined') return false;
  return document.cookie.includes('auth_token=') && !document.cookie.includes('auth_token=;');
}

interface AuthState {
  user: AuthUser | null;
  token: string | null;
  tenantId: string | null;
  isAuthenticated: boolean;

  login: (token: string, user: AuthUser, tenantId: string) => void;
  logout: () => void;
  setUser: (user: AuthUser) => void;
  /** Sincroniza estado con cookie: si no hay cookie, limpia sesión (para evitar botón "Iniciar sesión" oculto por localStorage obsoleto). */
  syncFromCookie: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      tenantId: null,
      isAuthenticated: false,

      login: (token, user, tenantId) => {
        if (typeof window !== 'undefined') {
          localStorage.setItem('auth_token', token);
          document.cookie = `auth_token=${encodeURIComponent(token)}; path=/; max-age=86400; SameSite=Lax`;
        }
        set({ token, user, tenantId, isAuthenticated: true });
      },

      logout: () => {
        if (typeof window !== 'undefined') {
          localStorage.removeItem('auth_token');
          document.cookie = 'auth_token=; path=/; max-age=0; SameSite=Lax';
        }
        set({ user: null, token: null, tenantId: null, isAuthenticated: false });
      },

      setUser: (user) => set({ user }),

      syncFromCookie: () => {
        if (!hasAuthCookie()) {
          if (typeof window !== 'undefined') {
            localStorage.removeItem('auth_token');
            document.cookie = 'auth_token=; path=/; max-age=0; SameSite=Lax';
          }
          set({ user: null, token: null, tenantId: null, isAuthenticated: false });
        }
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        user: state.user,
        tenantId: state.tenantId,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
