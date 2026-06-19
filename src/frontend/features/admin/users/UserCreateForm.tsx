'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import apiClient from '@/lib/http/apiClient';

export function UserCreateForm() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    
    const formData = new FormData(e.currentTarget);
    const payload = {
      tenant_id: formData.get('tenant_id'),
      full_name: formData.get('full_name'),
      email: formData.get('email'),
      password: formData.get('password'),
      role: formData.get('role'),
    };

    try {
      await apiClient.post('/users', payload);
      router.push('/admin/users');
      router.refresh();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Error al crear usuario');
      setLoading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto bg-white p-8 rounded-lg shadow">
      <h1 className="text-2xl font-bold mb-6">Crear Nuevo Usuario</h1>
      {error && <div className="mb-4 p-4 bg-red-100 text-red-700 rounded">{error}</div>}
      
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="tenant_id" className="block text-sm font-medium text-gray-700">ID del Tenant</label>
          <input id="tenant_id" required type="text" name="tenant_id" className="mt-1 block w-full rounded-md border-gray-300 shadow-sm border p-2" />
        </div>
        <div>
          <label htmlFor="full_name" className="block text-sm font-medium text-gray-700">Nombre Completo</label>
          <input id="full_name" required type="text" name="full_name" className="mt-1 block w-full rounded-md border-gray-300 shadow-sm border p-2" />
        </div>
        <div>
          <label htmlFor="email" className="block text-sm font-medium text-gray-700">Email</label>
          <input id="email" required type="email" name="email" className="mt-1 block w-full rounded-md border-gray-300 shadow-sm border p-2" />
        </div>
        <div>
          <label htmlFor="password" className="block text-sm font-medium text-gray-700">Contraseña</label>
          <input id="password" required type="password" name="password" minLength={8} className="mt-1 block w-full rounded-md border-gray-300 shadow-sm border p-2" />
        </div>
        <div>
          <label htmlFor="role" className="block text-sm font-medium text-gray-700">Rol</label>
          <select id="role" required name="role" className="mt-1 block w-full rounded-md border-gray-300 shadow-sm border p-2 bg-white">
            <option value="CUSTOMER">Customer</option>
            <option value="COMMERCIAL">Commercial</option>
            <option value="OPERATIONS">Operations</option>
            <option value="FINANCE">Finance</option>
            <option value="SUPERADMIN">Superadmin</option>
          </select>
        </div>
        
        <div className="pt-4 flex gap-4">
          <button type="button" onClick={() => router.push('/admin/users')} className="px-4 py-2 border rounded text-gray-600 hover:bg-gray-50">Cancelar</button>
          <button type="submit" disabled={loading} className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50">
            {loading ? 'Guardando...' : 'Crear Usuario'}
          </button>
        </div>
      </form>
    </div>
  );
}
