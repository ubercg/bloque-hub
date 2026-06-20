'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import apiClient from '@/lib/http/apiClient';
import { useUser } from './hooks/useUsers';

export function UserEditForm({ userId }: { userId: string }) {
  const router = useRouter();
  const { user, loading: userLoading, error: fetchError } = useUser(userId);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [password, setPassword] = useState('');

  const handleUpdate = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    
    const formData = new FormData(e.currentTarget);
    const payload: any = {
      tenant_id: formData.get('tenant_id'),
      full_name: formData.get('full_name'),
      email: formData.get('email'),
      role: formData.get('role'),
    };
    if (password) {
      payload.password = password;
    }

    try {
      await apiClient.patch(`/users/${userId}`, payload);
      router.push('/admin/users');
      router.refresh();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Error al actualizar usuario');
      setLoading(false);
    }
  };

  const handleToggleActive = async () => {
    if (!user) return;
    try {
      setLoading(true);
      setError(null);
      if (user.is_active) {
        await apiClient.delete(`/users/${userId}`);
      } else {
        await apiClient.patch(`/users/${userId}`, { is_active: true });
      }
      router.push('/admin/users');
      router.refresh();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Error al cambiar estado');
      setLoading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto bg-white p-8 rounded-lg shadow">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">
          {userLoading ? 'Cargando...' : user ? `Editar Usuario: ${user.full_name || user.email}` : 'Usuario'}
        </h1>
        {user && (
          <button 
            onClick={handleToggleActive} 
            disabled={loading}
            className={`px-4 py-2 rounded text-sm font-medium ${user.is_active ? 'bg-red-100 text-red-700 hover:bg-red-200' : 'bg-green-100 text-green-700 hover:bg-green-200'}`}
          >
            {user.is_active ? 'Desactivar Usuario' : 'Activar Usuario'}
          </button>
        )}
      </div>

      {fetchError && <div className="text-red-600 mb-4">{fetchError}</div>}
      {error && <div className="mb-4 p-4 bg-red-100 text-red-700 rounded">{error}</div>}
      
      {user && (
        <form onSubmit={handleUpdate} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">ID del Tenant (Mover de Tenant)</label>
            <input required type="text" name="tenant_id" defaultValue={user.tenant_id} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm border p-2" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Nombre Completo</label>
            <input required type="text" name="full_name" defaultValue={user.full_name} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm border p-2" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Email</label>
            <input required type="email" name="email" defaultValue={user.email} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm border p-2" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Rol</label>
            <select required name="role" defaultValue={user.role} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm border p-2 bg-white">
              <option value="CUSTOMER">Customer</option>
              <option value="COMMERCIAL">Commercial</option>
              <option value="OPERATIONS">Operations</option>
              <option value="FINANCE">Finance</option>
              <option value="SUPERADMIN">Superadmin</option>
            </select>
          </div>

          <div className="border-t pt-4 mt-4">
            <h3 className="text-lg font-medium mb-2">Restablecer Contraseña</h3>
            <p className="text-sm text-gray-500 mb-2">Deja en blanco para no modificar.</p>
            <input 
              type="password" 
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Nueva contraseña..." 
              minLength={8} 
              className="block w-full rounded-md border-gray-300 shadow-sm border p-2" 
            />
          </div>
          
          <div className="pt-4 flex gap-4">
            <button type="button" onClick={() => router.push('/admin/users')} className="px-4 py-2 border rounded text-gray-600 hover:bg-gray-50">Cancelar</button>
            <button type="submit" disabled={loading} className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50">
              {loading ? 'Guardando...' : 'Guardar Cambios'}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
