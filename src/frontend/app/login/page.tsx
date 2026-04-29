'use client';

/**
 * Página de inicio de sesión.
 * POST /api/auth/login con email/password; guarda JWT en cookie y redirige.
 */

import { Suspense, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { LogIn, LayoutGrid } from 'lucide-react';

import {
  getModulesForRole,
  loginWithCredentials,
  useAuthStore,
} from '@/features/auth';

function getRedirectByRole(role: string | undefined, fallback: string): string {
  const staffModules = getModulesForRole(role);
  if (staffModules.length > 0) return '/admin/dashboard';
  return fallback;
}

function LoginContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const login = useAuthStore((s) => s.login);
  const redirectParam = searchParams.get('redirect') ?? '/my-events';

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);
    try {
      const data = await loginWithCredentials(email, password);
      login(data.access_token, data.user, String(data.tenant_id));
      const target = getRedirectByRole(data.user?.role, redirectParam);
      router.push(target);
    } catch (err: unknown) {
      const res = err && typeof err === 'object' && 'response' in err
        ? (err as { response?: { status?: number } }).response
        : undefined;
      if (res?.status === 401) {
        setError('Email o contraseña incorrectos');
      } else {
        setError('Error al iniciar sesión. Intenta de nuevo.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="max-w-md w-full bg-white rounded-xl shadow-sm border border-gray-200 p-8">
        <div className="flex justify-center mb-6">
          <div className="w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center">
            <LogIn className="w-6 h-6 text-blue-600" />
          </div>
        </div>
        <h1 className="text-xl font-bold text-center text-gray-900 mb-2">
          Iniciar sesión
        </h1>
        <p className="text-sm text-gray-500 text-center mb-6">
          Ingresa tu correo y contraseña para acceder al portal.
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
              Correo electrónico
            </label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="tu@correo.com"
            />
          </div>
          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">
              Contraseña
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          {error && (
            <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </div>
          )}
          <button
            type="submit"
            disabled={isLoading}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? 'Iniciando sesión...' : 'Iniciar sesión'}
          </button>
        </form>

        <div className="mt-6 flex flex-col gap-3">
          <Link
            href="/catalog"
            className="flex items-center justify-center gap-2 px-4 py-3 rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50 font-medium"
          >
            <LayoutGrid className="w-4 h-4" />
            Ver catálogo sin iniciar sesión
          </Link>
        </div>
        <p className="mt-6 text-xs text-gray-400 text-center">
          Staff → Admin; Cliente → Mis eventos (o la URL que hayas indicado).
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-gray-50 flex items-center justify-center">
          <div className="text-gray-500">Cargando...</div>
        </div>
      }
    >
      <LoginContent />
    </Suspense>
  );
}
