import { useState, useEffect, useCallback } from 'react';
import apiClient from '@/lib/http/apiClient';

export interface User {
  id: string;
  tenant_id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export function useUsers() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchUsers = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const { data } = await apiClient.get<User[]>('/users');
      setUsers(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Error al cargar usuarios');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  return { users, loading, error, refetch: fetchUsers };
}

export function useUser(id: string) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchUser = useCallback(async () => {
    if (!id || id === 'create') return;
    try {
      setLoading(true);
      setError(null);
      const { data } = await apiClient.get<User>(`/users/${id}`);
      setUser(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Error al cargar usuario');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  return { user, loading, error, refetch: fetchUser };
}
