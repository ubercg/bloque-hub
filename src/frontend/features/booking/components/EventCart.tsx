'use client';

/**
 * Event Cart (Bandeja de Evento) - Floating cart widget
 * Multi-space cart for B2B reservations with availability validation
 */

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ShoppingCart, X, Calendar, Clock, MapPin, AlertTriangle } from 'lucide-react';

import apiClient from '@/lib/http/apiClient';
import { formatDateOnlyLocal } from '@/lib/dateUtils';

import {
  groupCartItemsBySpaceAndDate,
  itemKey,
  useEventCartStore,
} from '../store/event-cart.store';

function normalizeTime(t: string): string {
  if (!t) return '';
  const parts = t.split(':');
  if (parts.length >= 2) return `${parts[0].padStart(2, '0')}:${parts[1].padStart(2, '0')}`;
  return t;
}

export default function EventCart() {
  const router = useRouter();
  const { items, removeCartItem, clearCart, getTotalPrice, getItemCount } = useEventCartStore();
  const [conflictKeys, setConflictKeys] = useState<Set<string>>(new Set());
  const [checking, setChecking] = useState(false);

  const total = getTotalPrice();
  const itemCount = getItemCount();
  const groups = useMemo(() => groupCartItemsBySpaceAndDate(items), [items]);

  useEffect(() => {
    if (items.length === 0) {
      setConflictKeys(new Set());
      return;
    }
    let cancelled = false;

    const check = async () => {
      setChecking(true);
      try {
        const res = await apiClient.post('spaces/check-availability-group', {
          items: items.map((item) => ({
            espacio_id: item.spaceId,
            fecha: item.fecha,
            hora_inicio: normalizeTime(item.horaInicio) + ':00',
            hora_fin: normalizeTime(item.horaFin) + ':00',
          })),
        });
        if (cancelled) return;
        const { conflicts } = res.data as {
          all_available: boolean;
          conflicts: { espacio_id: string; estado: string; motivo: string }[];
        };
        const conflictSpaceIds = new Set(conflicts.map((c) => c.espacio_id));
        const newConflicts = new Set<string>();
        for (const item of items) {
          if (conflictSpaceIds.has(item.spaceId)) {
            newConflicts.add(itemKey(item));
          }
        }
        if (!cancelled) setConflictKeys(newConflicts);
      } catch {
        if (!cancelled) {
          setConflictKeys(new Set(items.map(itemKey)));
        }
      }
      if (!cancelled) setChecking(false);
    };

    check();
    const interval = setInterval(check, 5000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [items]);

  const hasConflicts = conflictKeys.size > 0;
  const handleCheckout = () => {
    if (hasConflicts) return;
    router.push('/booking/confirm');
  };

  if (itemCount === 0) {
    return (
      <div className="fixed bottom-6 right-6 bg-white shadow-lg rounded-full p-4 border-2 border-gray-200">
        <div className="flex items-center gap-2 text-gray-400">
          <ShoppingCart className="w-6 h-6" />
          <span className="text-sm font-medium">Carrito vacío</span>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 bg-white shadow-2xl rounded-2xl w-96 max-h-[600px] flex flex-col border border-gray-200">
      <div className="p-4 border-b border-gray-200 flex items-center justify-between bg-gradient-to-r from-blue-50 to-purple-50">
        <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2">
          <ShoppingCart className="w-5 h-5 text-blue-600" />
          Bandeja de Evento ({itemCount})
        </h3>
        <button
          onClick={clearCart}
          className="text-sm text-gray-500 hover:text-red-600 transition font-medium"
          title="Limpiar carrito"
        >
          Limpiar
        </button>
      </div>

      {hasConflicts && (
        <div className="mx-4 mt-2 p-3 bg-amber-50 border border-amber-200 rounded-lg flex items-start gap-2">
          <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-amber-800">
            Algunos espacios ya no están disponibles en el horario seleccionado. Quita los marcados o elige otro horario para continuar.
          </p>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {groups.map((group) => {
          const groupSubtotal = group.items.reduce((s, i) => s + i.precio, 0);
          return (
            <div
              key={group.key}
              className="rounded-xl border border-gray-200 bg-gray-50/80 overflow-hidden shadow-sm"
            >
              <div className="px-3 py-2.5 bg-gradient-to-r from-slate-50 to-blue-50/60 border-b border-gray-200">
                <div className="font-semibold text-gray-900 flex items-center gap-2">
                  <MapPin className="w-4 h-4 text-blue-600 flex-shrink-0" />
                  <span className="truncate">{group.spaceName}</span>
                </div>
                <div className="text-xs text-gray-600 mt-1 flex items-center gap-1">
                  <Calendar className="w-3 h-3 flex-shrink-0" />
                  {formatDateOnlyLocal(group.fecha)}
                </div>
              </div>

              <ul className="divide-y divide-gray-100">
                {group.items.map((item) => {
                  const isConflict = conflictKeys.has(itemKey(item));
                  return (
                    <li
                      key={itemKey(item)}
                      className={`flex items-start justify-between gap-2 px-3 py-2.5 ${
                        isConflict ? 'bg-amber-50/90' : 'bg-white'
                      }`}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5 text-sm text-gray-800">
                          <Clock className="w-3.5 h-3.5 text-gray-500 flex-shrink-0" />
                          <span>
                            {item.horaInicio} – {item.horaFin}
                          </span>
                        </div>
                        <div className="text-xs font-semibold text-blue-600 mt-0.5 pl-5">
                          ${item.precio.toLocaleString()} MXN
                        </div>
                        {isConflict && (
                          <p className="text-[10px] text-amber-800 mt-1 pl-5">Conflicto de disponibilidad</p>
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={() => removeCartItem(itemKey(item))}
                        className="text-gray-400 hover:text-red-600 transition flex-shrink-0 p-0.5"
                        title="Quitar este horario"
                        aria-label={`Quitar horario ${item.horaInicio}–${item.horaFin}`}
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </li>
                  );
                })}
              </ul>

              {group.items.length > 1 && (
                <div className="px-3 py-1.5 text-xs text-gray-500 border-t border-gray-100 bg-gray-50/50 flex justify-between">
                  <span>Subtotal ({group.items.length} horarios)</span>
                  <span className="font-medium text-gray-700">
                    ${groupSubtotal.toLocaleString()} MXN
                  </span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="p-4 border-t border-gray-200 bg-gray-50">
        <div className="flex items-center justify-between mb-4">
          <span className="text-sm font-medium text-gray-700">Total:</span>
          <span className="text-2xl font-bold text-blue-600">${total.toLocaleString()} MXN</span>
        </div>

        <button
          onClick={handleCheckout}
          disabled={hasConflicts || checking}
          className="w-full py-3 rounded-lg font-semibold transition shadow-md hover:shadow-lg disabled:opacity-50 disabled:cursor-not-allowed bg-blue-600 text-white hover:bg-blue-700"
        >
          {checking ? 'Verificando disponibilidad...' : 'Continuar con Reserva →'}
        </button>

        <p className="text-xs text-gray-500 text-center mt-2">
          {hasConflicts
            ? 'Resuelve los conflictos de disponibilidad para continuar'
            : 'Podrás revisar los detalles antes de confirmar'}
        </p>
      </div>
    </div>
  );
}

