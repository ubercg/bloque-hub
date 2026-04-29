'use client';

/**
 * Operations: single service order checklist. Mark items COMPLETED via PATCH.
 * Offline: queue mutations in IndexedDB and sync when back online.
 */

import { useCallback, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import apiClient from '@/lib/http/apiClient';
import {
  addPendingMutation,
  cacheOrder,
  clearPendingMutations,
  getCachedOrder,
  getPendingMutations,
  removePendingMutation,
} from '@/lib/operationsDb';
import { ArrowLeft, Check, Loader2, Circle } from 'lucide-react';

interface Item {
  id: string;
  title: string;
  item_order: number;
  is_critical: boolean;
  status: string;
}

interface Checklist {
  id: string;
  name: string;
  items: Item[];
}

interface Order {
  id: string;
  status: string;
  checklists: Checklist[];
}

export default function OrderChecklistPage() {
  const params = useParams();
  const router = useRouter();
  const orderId = params?.orderId as string;
  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [patching, setPatching] = useState<Set<string>>(new Set());

  const fetchOrder = useCallback(() => {
    if (!orderId) return;
    setLoading(true);
    apiClient
      .get<Order>(`/service-orders/${orderId}`)
      .then((res) => {
        setOrder(res.data);
        cacheOrder(orderId, res.data).catch(() => {});
      })
      .catch(async () => {
        try {
          const cached = await getCachedOrder(orderId);
          if (cached) setOrder(cached as Order);
          else setError('No se pudo cargar la orden');
        } catch {
          setError('No se pudo cargar la orden');
        }
      })
      .finally(() => setLoading(false));
  }, [orderId]);

  useEffect(() => {
    fetchOrder();
  }, [fetchOrder]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const flush = async () => {
      const pending = await getPendingMutations();
      for (const m of pending) {
        try {
          await apiClient.patch(`/service-order-items/${m.itemId}`, { status: m.status });
          await removePendingMutation(m.id);
        } catch {
          break;
        }
      }
      fetchOrder();
    };
    const onOnline = () => flush();
    window.addEventListener('online', onOnline);
    return () => window.removeEventListener('online', onOnline);
  }, [fetchOrder]);

  const toggleItem = (item: Item) => {
    if (patching.has(item.id)) return;
    const nextStatus = item.status === 'COMPLETED' ? 'PENDING' : 'COMPLETED';
    setPatching((s) => new Set(s).add(item.id));

    const applyOptimistic = (o: Order | null) => {
      if (!o) return;
      const next = JSON.parse(JSON.stringify(o)) as Order;
      for (const c of next.checklists || []) {
        for (const i of c.items || []) {
          if (i.id === item.id) {
            i.status = nextStatus;
            break;
          }
        }
      }
      setOrder(next);
    };

    if (!navigator.onLine) {
      addPendingMutation(item.id, nextStatus).then(() => {
        applyOptimistic(order);
        setPatching((s) => { const n = new Set(s); n.delete(item.id); return n; });
      });
      return;
    }

    apiClient
      .patch(`/service-order-items/${item.id}`, { status: nextStatus })
      .then(() => fetchOrder())
      .catch(() => setError('Error al actualizar'))
      .finally(() => setPatching((s) => { const n = new Set(s); n.delete(item.id); return n; }));
  };

  if (!orderId) return null;
  if (loading && !order) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
      </div>
    );
  }
  if (error && !order) {
    return (
      <div className="space-y-4">
        <Link href="/operations/checklists" className="inline-flex items-center gap-2 text-blue-600">
          <ArrowLeft className="w-4 h-4" /> Volver
        </Link>
        <p className="text-red-600">{error}</p>
      </div>
    );
  }
  if (!order) return null;

  return (
    <div className="space-y-6">
      <Link
        href="/operations/checklists"
        className="inline-flex items-center gap-2 text-blue-600 hover:underline"
      >
        <ArrowLeft className="w-4 h-4" /> Volver a órdenes
      </Link>
      <h1 className="text-2xl font-bold text-gray-900">
        Orden {order.id.slice(0, 8)}… · {order.status}
      </h1>
      {order.checklists?.map((checklist) => (
        <div key={checklist.id} className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <h2 className="px-4 py-3 bg-gray-50 font-semibold text-gray-900 border-b border-gray-200">
            {checklist.name}
          </h2>
          <ul className="divide-y divide-gray-100">
            {checklist.items?.map((item) => (
              <li key={item.id} className="flex items-center gap-4 px-4 py-3">
                <button
                  type="button"
                  onClick={() => toggleItem(item)}
                  disabled={patching.has(item.id)}
                  className={`flex-shrink-0 w-8 h-8 rounded-full border-2 flex items-center justify-center transition disabled:opacity-50 ${
                    item.status === 'COMPLETED' ? 'border-green-500 bg-green-500' : 'border-gray-300 bg-white'
                  }`}
                >
                  {patching.has(item.id) ? (
                    <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
                  ) : item.status === 'COMPLETED' ? (
                    <Check className="w-4 h-5 text-white" />
                  ) : (
                    <Circle className="w-4 h-4 text-gray-400" />
                  )}
                </button>
                <div className="flex-1 min-w-0">
                  <span className={item.status === 'COMPLETED' ? 'text-gray-500 line-through' : 'text-gray-900'}>
                    {item.title}
                  </span>
                  {item.is_critical && (
                    <span className="ml-2 text-xs font-medium text-amber-600">Crítico</span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
