'use client';

/**
 * Wizard Step 2 — Espacio / fecha / cotización (REQ-012 §4, RN-012).
 * Visual calculator: space picker + AvailabilityCalendar + bandeja (like catalog
 * booking). Prices come from public price-preview (advisory; submit recomputes).
 */

import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import {
  Calendar,
  Clock,
  DollarSign,
  Loader2,
  MapPin,
  ShoppingCart,
  Users,
  X,
} from 'lucide-react';

import { AvailabilityCalendar } from '@/features/catalog';
import apiClient from '@/lib/http/apiClient';
import { formatDateOnlyLocal } from '@/lib/dateUtils';

import { SpaceOrderDetail } from './SpaceOrderDetail';
import { useQuoteWizardStore } from '../store/quote-wizard.store';
import type { WizardItem } from '../store/quote-wizard.store';

interface SpaceOption {
  id: string;
  name: string;
  slug: string;
  capacidad_maxima: number;
  precio_por_hora: number;
  piso?: number | null;
  descripcion?: string | null;
}

function normalizeTime(t: string): string {
  return t.slice(0, 5);
}

function wizardItemKey(item: WizardItem): string {
  return `${item.spaceId}|${item.fecha}|${normalizeTime(item.horaInicio)}|${normalizeTime(item.horaFin)}`;
}

interface WizardGroup {
  key: string;
  spaceId: string;
  spaceName: string;
  fecha: string;
  items: WizardItem[];
}

function groupWizardItems(
  items: WizardItem[],
  spaceNameOf: (id: string) => string
): WizardGroup[] {
  const map = new Map<string, WizardGroup>();
  for (const item of items) {
    const key = `${item.spaceId}|${item.fecha}`;
    let group = map.get(key);
    if (!group) {
      group = {
        key,
        spaceId: item.spaceId,
        spaceName: spaceNameOf(item.spaceId),
        fecha: item.fecha,
        items: [],
      };
      map.set(key, group);
    }
    group.items.push(item);
  }
  for (const group of map.values()) {
    group.items.sort((a, b) => a.horaInicio.localeCompare(b.horaInicio));
  }
  return Array.from(map.values()).sort((a, b) => {
    const byDate = a.fecha.localeCompare(b.fecha);
    if (byDate !== 0) return byDate;
    return a.spaceName.localeCompare(b.spaceName, 'es');
  });
}

const NO_PRICING_MESSAGE = 'No hay una regla de precio configurada para este espacio en esa fecha.';
const GENERIC_ERROR_MESSAGE = 'No se pudo calcular la cotización. Intenta de nuevo.';

export function StepEspacio() {
  const items = useQuoteWizardStore((s) => s.items);
  const removeItemBySlot = useQuoteWizardStore((s) => s.removeItemBySlot);
  const setItems = useQuoteWizardStore((s) => s.setItems);
  const discountCode = useQuoteWizardStore((s) => s.discountCode);
  const discountAmount = useQuoteWizardStore((s) => s.discountAmount);
  const setField = useQuoteWizardStore((s) => s.setField);
  const fechaTentativa = useQuoteWizardStore((s) => s.fechaTentativa);
  const espacioRequerido = useQuoteWizardStore((s) => s.espacioRequerido);

  const [spaces, setSpaces] = useState<SpaceOption[]>([]);
  const [spacesLoading, setSpacesLoading] = useState(true);
  const [selectedSpaceId, setSelectedSpaceId] = useState<string>('');
  const [addingSlotKey, setAddingSlotKey] = useState<string | null>(null);
  const [repricing, setRepricing] = useState(false);
  const [hourlyRateBySpace, setHourlyRateBySpace] = useState<Record<string, number>>({});

  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<Array<{ space_id: string; extra_hour_rate: number | string }>>('/pricing-rules')
      .then((res) => {
        if (cancelled) return;
        const map: Record<string, number> = {};
        for (const rule of res.data) {
          map[rule.space_id] = Number(rule.extra_hour_rate);
        }
        setHourlyRateBySpace(map);
      })
      .catch(() => {
        if (!cancelled) setHourlyRateBySpace({});
      });
    return () => {
      cancelled = true;
    };
  }, []);

  /** Reprice all slots merging contiguous blocks (package tariff). */
  const repriceAll = async (nextItems: WizardItem[]): Promise<WizardItem[] | null> => {
    if (nextItems.length === 0) return [];
    const priceRes = await apiClient.post('/public/quote-requests/price-preview', {
      items: nextItems.map((item) => ({
        space_id: item.spaceId,
        fecha: item.fecha,
        hora_inicio: item.horaInicio,
        hora_fin: item.horaFin,
      })),
    });
    const priced = priceRes.data.items as Array<{ price: number }>;
    if (!Array.isArray(priced) || priced.length !== nextItems.length) {
      return null;
    }
    return nextItems.map((item, i) => ({
      ...item,
      cotizacionCalculada: priced[i]?.price,
    }));
  };

  useEffect(() => {
    let cancelled = false;
    setSpacesLoading(true);
    apiClient
      .get<SpaceOption[]>('/spaces')
      .then((res) => {
        if (!cancelled) setSpaces(res.data);
      })
      .catch(() => {
        if (!cancelled) setSpaces([]);
      })
      .finally(() => {
        if (!cancelled) setSpacesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedSpace = spaces.find((s) => s.id === selectedSpaceId) ?? null;
  const groups = useMemo(() => {
    const nameOf = (spaceId: string) => spaces.find((s) => s.id === spaceId)?.name ?? spaceId;
    return groupWizardItems(items, nameOf);
  }, [items, spaces]);
  const total = items.reduce((acc, item) => acc + (item.cotizacionCalculada ?? 0), 0);

  const selectedSlotsForCalendar = useMemo(
    () =>
      items
        .filter((i) => i.spaceId === selectedSpaceId)
        .map((i) => ({
          fecha: i.fecha,
          hora_inicio: i.horaInicio,
          hora_fin: i.horaFin,
        })),
    [items, selectedSpaceId]
  );

  const handleSlotSelect = async (slot: {
    fecha: string;
    hora_inicio: string;
    hora_fin: string;
  }) => {
    if (!selectedSpace) return;

    const horaInicio = normalizeTime(slot.hora_inicio);
    const horaFin = normalizeTime(slot.hora_fin);
    const pendingKey = `${selectedSpace.id}|${slot.fecha}|${horaInicio}|${horaFin}`;

    const alreadyAdded = items.some(
      (i) =>
        i.spaceId === selectedSpace.id &&
        i.fecha === slot.fecha &&
        normalizeTime(i.horaInicio) === horaInicio &&
        normalizeTime(i.horaFin) === horaFin
    );
    if (alreadyAdded) {
      toast.message('Ese horario ya está en tu cotización.');
      return;
    }

    const nextItems: WizardItem[] = [
      ...items,
      {
        spaceId: selectedSpace.id,
        fecha: slot.fecha,
        horaInicio,
        horaFin,
      },
    ];

    setAddingSlotKey(pendingKey);
    setRepricing(true);
    try {
      const priced = await repriceAll(nextItems);
      if (!priced) {
        toast.error(GENERIC_ERROR_MESSAGE);
        return;
      }
      setItems(priced);
      toast.success('Horario añadido a la cotización.');
    } catch (err: unknown) {
      const status =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { status?: number } }).response?.status
          : undefined;
      toast.error(status === 422 ? NO_PRICING_MESSAGE : GENERIC_ERROR_MESSAGE);
    } finally {
      setAddingSlotKey(null);
      setRepricing(false);
    }
  };

  const handleRemoveSlot = async (item: WizardItem) => {
    const nextItems = items.filter(
      (i) =>
        !(
          i.spaceId === item.spaceId &&
          i.fecha === item.fecha &&
          normalizeTime(i.horaInicio) === normalizeTime(item.horaInicio) &&
          normalizeTime(i.horaFin) === normalizeTime(item.horaFin)
        )
    );
    if (nextItems.length === items.length) return;

    setRepricing(true);
    try {
      if (nextItems.length === 0) {
        setItems([]);
        return;
      }
      const priced = await repriceAll(nextItems);
      if (!priced) {
        // Fall back to local remove without prices rather than blocking UX.
        removeItemBySlot(item);
        toast.error(GENERIC_ERROR_MESSAGE);
        return;
      }
      setItems(priced);
    } catch {
      removeItemBySlot(item);
      toast.error(GENERIC_ERROR_MESSAGE);
    } finally {
      setRepricing(false);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">2. Espacio, fecha y cotización</h2>
        <p className="text-xs text-gray-500 mt-1">
          Elige un espacio, un día y horarios disponibles. La cotización es preliminar; el precio
          final se confirma al enviar tu solicitud.
        </p>
      </div>

      {(fechaTentativa || espacioRequerido) && (
        // Reference-only display from BLOQUE Portal's lead_prefill (RN-015, RN-022).
        // Never bound to an input, addItem, a date default, or a space_id lookup.
        <div
          role="note"
          aria-label="Referencia de tu solicitud en BLOQUE Portal"
          className="rounded-lg border border-blue-100 bg-blue-50/60 px-4 py-3 text-sm text-blue-950"
        >
          <p className="font-medium mb-1">Referencia de tu solicitud en BLOQUE Portal</p>
          {fechaTentativa && <p>Fecha tentativa indicada: {fechaTentativa}</p>}
          {espacioRequerido && <p>Espacio solicitado: {espacioRequerido}</p>}
          <p className="text-xs text-blue-900/70 mt-1">
            Esta información es solo de referencia. Elige el espacio y horario disponibles abajo.
          </p>
        </div>
      )}

      {spacesLoading ? (
        <div className="flex items-center justify-center gap-2 py-12 text-gray-500">
          <Loader2 className="w-5 h-5 animate-spin" aria-hidden />
          Cargando espacios…
        </div>
      ) : spaces.length === 0 ? (
        <p role="alert" className="text-sm text-red-600">
          No hay espacios disponibles en este momento.
        </p>
      ) : (
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">Espacio</label>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {spaces.map((space) => {
              const isActive = space.id === selectedSpaceId;
              return (
                <button
                  key={space.id}
                  type="button"
                  onClick={() => setSelectedSpaceId(space.id)}
                  className={`text-left rounded-xl border px-3 py-3 transition focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                    isActive
                      ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-400'
                      : 'border-gray-200 bg-white hover:border-blue-300 hover:bg-gray-50'
                  }`}
                  aria-pressed={isActive}
                >
                  <span className="font-medium text-gray-900 block truncate">{space.name}</span>
                  <span className="text-xs text-gray-500 mt-0.5 block">
                    {space.capacidad_maxima} pers.
                    {typeof space.piso === 'number' ? ` · Piso ${space.piso}` : ''}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {selectedSpace && (
        <div className="rounded-2xl border border-gray-200 overflow-hidden">
          <div className="relative bg-gradient-to-br from-[#1e3a8a] via-[#2563eb] to-[#1d4ed8] px-4 py-6 text-white">
            <div className="flex items-center gap-2">
              <MapPin className="w-5 h-5 opacity-90" aria-hidden />
              <h3 className="text-xl font-semibold tracking-tight">{selectedSpace.name}</h3>
            </div>
            <p className="text-sm text-white/85 mt-1">
              Piso {selectedSpace.piso ?? '—'}
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-0 md:gap-0 bg-white">
            <div className="md:col-span-2 p-4 sm:p-5 border-b md:border-b-0 md:border-r border-gray-100 space-y-4">
              {selectedSpace.descripcion ? (
                <p className="text-sm text-gray-600 leading-relaxed line-clamp-3">
                  {selectedSpace.descripcion}
                </p>
              ) : null}

              <div>
                <h4 className="text-sm font-semibold text-gray-800 mb-1">Disponibilidad</h4>
                <p className="text-xs text-gray-500 mb-3">
                  Elige un día y un horario en verde para agregarlo a tu cotización.
                </p>
                {addingSlotKey || repricing ? (
                  <p className="text-xs text-blue-600 mb-2 flex items-center gap-1.5">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden />
                    Calculando precio del bloque…
                  </p>
                ) : null}
                <AvailabilityCalendar
                  spaceId={selectedSpace.id}
                  onSlotSelect={handleSlotSelect}
                  selectedSlots={selectedSlotsForCalendar}
                />
              </div>
            </div>

            <aside className="p-4 sm:p-5 bg-gray-50/80 space-y-4">
              <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
                <h4 className="text-sm font-semibold text-gray-800 mb-3">Características</h4>
                <ul className="space-y-2.5 text-sm text-gray-600">
                  <li className="flex items-center gap-2">
                    <Users className="w-4 h-4 text-blue-600 shrink-0" aria-hidden />
                    {selectedSpace.capacidad_maxima} personas
                  </li>
                  <li className="flex items-center gap-2">
                    <DollarSign className="w-4 h-4 text-emerald-600 shrink-0" aria-hidden />
                    <span>
                      $
                      {(
                        hourlyRateBySpace[selectedSpace.id] ?? selectedSpace.precio_por_hora
                      ).toLocaleString('es-MX')}{' '}
                      MXN / hora
                      <span className="block text-[11px] text-gray-400 font-normal">
                        Tarifa de catálogo (hora suelta); bloques usan paquetes 6h/12h
                      </span>
                    </span>
                  </li>
                </ul>
              </div>

              <WizardBandeja
                groups={groups}
                total={total}
                itemCount={items.length}
                onRemove={handleRemoveSlot}
                repricing={repricing}
              />
            </aside>
          </div>
        </div>
      )}

      {!selectedSpace && items.length > 0 && (
        <WizardBandeja
          groups={groups}
          total={total}
          itemCount={items.length}
          onRemove={handleRemoveSlot}
          repricing={repricing}
        />
      )}

      {items.length > 0 && (
        <SpaceOrderDetail
          items={items}
          spaces={spaces}
          appliedDiscountCode={discountCode}
          discountAmount={discountAmount}
          onDiscountApplied={(code, amount) => {
            setField('discountCode', code);
            setField('discountAmount', amount);
          }}
        />
      )}
    </div>
  );
}

function WizardBandeja({
  groups,
  total,
  itemCount,
  onRemove,
  repricing = false,
}: {
  groups: WizardGroup[];
  total: number;
  itemCount: number;
  onRemove: (item: WizardItem) => void;
  repricing?: boolean;
}) {
  if (itemCount === 0) {
    return (
      <div className="bg-white rounded-xl border border-dashed border-gray-300 p-4 text-center text-sm text-gray-400">
        <ShoppingCart className="w-5 h-5 mx-auto mb-1 opacity-60" aria-hidden />
        Sin horarios aún
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden flex flex-col max-h-[420px]">
      <div className="px-3 py-2.5 border-b border-gray-200 bg-gradient-to-r from-blue-50 to-slate-50 flex items-center gap-2">
        <ShoppingCart className="w-4 h-4 text-blue-600" aria-hidden />
        <h4 className="text-sm font-bold text-gray-900">Bandeja de cotización ({itemCount})</h4>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {groups.map((group) => {
          const groupSubtotal = group.items.reduce(
            (s, item) => s + (item.cotizacionCalculada ?? 0),
            0
          );
          return (
            <div
              key={group.key}
              className="rounded-lg border border-gray-200 bg-gray-50/80 overflow-hidden"
            >
              <div className="px-2.5 py-2 bg-slate-50 border-b border-gray-200">
                <div className="font-semibold text-sm text-gray-900 flex items-center gap-1.5">
                  <MapPin className="w-3.5 h-3.5 text-blue-600 shrink-0" aria-hidden />
                  <span className="truncate">{group.spaceName}</span>
                </div>
                <div className="text-[11px] text-gray-600 mt-0.5 flex items-center gap-1">
                  <Calendar className="w-3 h-3 shrink-0" aria-hidden />
                  {formatDateOnlyLocal(group.fecha)}
                </div>
              </div>
              <ul className="divide-y divide-gray-100">
                {group.items.map((item) => (
                  <li
                    key={wizardItemKey(item)}
                    className="flex items-start justify-between gap-2 px-2.5 py-2 bg-white"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-1 text-sm text-gray-800">
                        <Clock className="w-3.5 h-3.5 text-gray-500 shrink-0" aria-hidden />
                        {normalizeTime(item.horaInicio)} – {normalizeTime(item.horaFin)}
                      </div>
                      {typeof item.cotizacionCalculada === 'number' && (
                        <div className="text-xs font-semibold text-blue-600 mt-0.5 pl-5">
                          ${item.cotizacionCalculada.toLocaleString('es-MX')} MXN
                        </div>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => onRemove(item)}
                      className="text-gray-400 hover:text-red-600 p-0.5"
                      aria-label={`Quitar horario ${normalizeTime(item.horaInicio)}–${normalizeTime(item.horaFin)}`}
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </li>
                ))}
              </ul>
              {group.items.length > 1 && (
                <div className="px-2.5 py-1.5 text-[11px] text-gray-500 border-t border-gray-100 flex justify-between">
                  <span>Subtotal ({group.items.length} horarios)</span>
                  <span className="font-medium text-gray-700">
                    ${groupSubtotal.toLocaleString('es-MX')} MXN
                  </span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="px-3 py-3 border-t border-gray-200 bg-gray-50 flex items-center justify-between">
        <span className="text-sm font-medium text-gray-700">
          {repricing ? 'Recalculando…' : 'Total preliminar'}
        </span>
        <span className="text-xl font-bold text-blue-600">
          ${total.toLocaleString('es-MX')} MXN
        </span>
      </div>
    </div>
  );
}
