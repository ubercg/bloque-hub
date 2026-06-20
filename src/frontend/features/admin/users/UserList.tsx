'use client';

import React from 'react';
import Link from 'next/link';
import { useUsers } from './hooks/useUsers';
import { Loader2, Plus } from 'lucide-react';

export function UserList() {
  const { users, loading, error } = useUsers();

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">Administración de Usuarios</h1>
        <Link href="/admin/users/create" className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
          <Plus className="w-4 h-4" /> Nuevo Usuario
        </Link>
      </div>
      
      {loading ? (
        <div className="flex justify-center p-8"><Loader2 className="w-8 h-8 animate-spin" /></div>
      ) : error ? (
        <div className="p-4 bg-red-100 text-red-700 rounded" data-testid="error-message">{error}</div>
      ) : (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Nombre</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Email</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Rol</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Estado</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Acciones</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {users.map(user => (
                <tr key={user.id}>
                  <td className="px-6 py-4 whitespace-nowrap">{user.full_name}</td>
                  <td className="px-6 py-4 whitespace-nowrap">{user.email}</td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-blue-100 text-blue-800">
                      {user.role}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${user.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                      {user.is_active ? 'Activo' : 'Inactivo'}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                    <Link href={`/admin/users/${user.id}`} className="text-blue-600 hover:text-blue-900">
                      Editar
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {users.length === 0 && <div className="p-8 text-center text-gray-500">No hay usuarios.</div>}
        </div>
      )}
    </div>
  );
}
