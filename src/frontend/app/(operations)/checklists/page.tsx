'use client';

/**
 * Operations: list of service orders (checklists).
 * Fetches GET /api/service-orders. Offline: show cached data from IndexedDB.
 */

import { useEffect, useState } from 'react';
import Link from 'next/link';
import apiClient from '@/lib/http/apiClient';
import { cacheOrdersList, getCachedOrdersList } from '@/lib/operationsDb';
import { Loader2, Package, WifiOff } from 'lucide-react';

interface ServiceOrder {
  id: string;
  status: string;
  reservation_id: string | null;
  created_at: string;
  checklists: { id: string; name: string; items: { id: string; status: string; is_critical: boolean }[] }[];
}

export default function OperationsChecklistsPage() {
  const [orders, setOrders] = useState<ServiceOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    apiClient
      .get<ServiceOrder[]>('/service-orders')
      .then((res) => {
        if (!cancelled) {
          const data = res.data || [];
          setOrders(data);
          setOffline(false);
          cacheOrdersList(data).catch(() => {});
        }
      })
      .catch(async (err) => {
        if (!cancelled) {
          if (err.message === 'Network Error' || (typeof navigator !== 'undefined' && !navigator.onLine)) {
            setOffline(true);
            try {
              const cached = await getCachedOrdersList();
              setOrders((cached as ServiceOrder[]) || []);
            } catch {
              setOrders([]);
            }
          } else {
            setError(err.response?.data?.detail || 'Error al cargar órdenes');
          }
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  if (loading && orders.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-gray-900">Órdenes de servicio</h1>
      {offline && (
        <div className="flex items-center gap-2 p-3 bg-amber-50 border border-amber-200 rounded-lg text-amber-800">
          <WifiOff className="w-5 h-5" />
          <span>Sin conexión. Los cambios se sincronizarán al recuperar la red.</span>
        </div>
      )}
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-800">
          {error}
        </div>
      )}
      {orders.length === 0 && !loading && (
        <p className="text-gray-500">No hay órdenes de servicio.</p>
      )}
      <ul className="space-y-3">
        {orders.map((order) => {
          const totalItems = order.checklists?.reduce((acc, c) => acc + (c.items?.length || 0), 0) || 0;
          const completed = order.checklists?.reduce(
            (acc, c) => acc + (c.items?.filter((i) => i.status === 'COMPLETED').length || 0),
            0
          ) || 0;
          return (
            <li key={order.id}>
              <Link
                href={`/operations/checklists/${order.id}`}
                className="block p-4 bg-white rounded-xl border border-gray-200 shadow-sm hover:border-blue-300 hover:shadow transition"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Package className="w-8 h-8 text-blue-600" />
                    <div>
                      <div className="font-semibold text-gray-900">
                        OS {order.id.slice(0, 8)}…
                      </div>
                      <div className="text-sm text-gray-500">
                        {completed}/{totalItems} tareas · {order.status}
                      </div>
                    </div>
                  </div>
                  <span className="text-blue-600 font-medium">Ver checklist →</span>
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
