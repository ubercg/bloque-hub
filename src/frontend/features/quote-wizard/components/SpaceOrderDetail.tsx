'use client';

/**
 * Detalle de Espacios — same table + discount UI as booking/confirm.
 * Reuses buildOrderTableRows; totals come from wizard price-preview amounts.
 */

import { useEffect, useMemo, useState } from 'react';

import {
  buildOrderTableRows,
  type PricingBySpaceId,
} from '@/features/booking/lib/confirm-summary';
import type { EventCartItem } from '@/features/booking';
import apiClient from '@/lib/http/apiClient';

import type { WizardItem } from '../store/quote-wizard.store';

interface SpaceRef {
  id: string;
  name: string;
  precio_por_hora: number;
}

interface PricingRuleApi {
  space_id: string;
  base_6h: number;
  base_12h: number;
  extra_hour_rate: number;
}

interface DiscountValidateResponse {
  valid: boolean;
  code: string;
  discount_amount: string | number;
  reason?: string | null;
}

function formatCantidad(n: number): string {
  if (Number.isInteger(n)) return String(n);
  return n.toLocaleString('es-MX', { maximumFractionDigits: 2 });
}

function normalizeTime(t: string): string {
  return t.slice(0, 5);
}

const DISCOUNT_REASON_MESSAGES: Record<string, string> = {
  DISCOUNT_CODE_INVALID: 'El código no existe.',
  DISCOUNT_CODE_INACTIVE: 'El código está inactivo.',
  DISCOUNT_CODE_EXPIRED: 'El código está expirado.',
  DISCOUNT_CODE_USAGE_LIMIT_REACHED: 'El código alcanzó su límite de usos.',
  DISCOUNT_CODE_MIN_SUBTOTAL_NOT_MET: 'El subtotal no cumple el mínimo para usar este código.',
  DISCOUNT_CODE_ALREADY_USED_BY_USER: 'Ya usaste este código anteriormente.',
};

interface Props {
  items: WizardItem[];
  spaces: SpaceRef[];
  appliedDiscountCode: string | null;
  discountAmount: number;
  onDiscountApplied: (code: string | null, amount: number) => void;
}

export function SpaceOrderDetail({
  items,
  spaces,
  appliedDiscountCode,
  discountAmount,
  onDiscountApplied,
}: Props) {
  const [pricingRules, setPricingRules] = useState<PricingRuleApi[]>([]);
  const [discountCodeInput, setDiscountCodeInput] = useState('');
  const [discountMessage, setDiscountMessage] = useState<string | null>(null);
  const [validatingDiscount, setValidatingDiscount] = useState(false);

  useEffect(() => {
    if (appliedDiscountCode) {
      setDiscountCodeInput(appliedDiscountCode);
    }
  }, [appliedDiscountCode]);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<PricingRuleApi[]>('/pricing-rules')
      .then((res) => {
        if (!cancelled) setPricingRules(res.data);
      })
      .catch(() => {
        // Anonymous wizard: endpoint requires auth — fall back to space hourly rates.
        if (!cancelled) setPricingRules([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const cartItems: EventCartItem[] = useMemo(() => {
    return items.map((item) => ({
      spaceId: item.spaceId,
      spaceName: spaces.find((s) => s.id === item.spaceId)?.name ?? item.spaceId,
      fecha: item.fecha,
      horaInicio: normalizeTime(item.horaInicio),
      horaFin: normalizeTime(item.horaFin),
      precio: item.cotizacionCalculada ?? 0,
    }));
  }, [items, spaces]);

  const pricingBySpaceId = useMemo<PricingBySpaceId>(() => {
    const byId: PricingBySpaceId = {};
    const rulesMap = new Map(pricingRules.map((r) => [r.space_id, r]));
    for (const s of spaces) {
      const rule = rulesMap.get(s.id);
      byId[s.id] = {
        porHora: rule?.extra_hour_rate ?? s.precio_por_hora ?? 0,
        seisHoras: rule?.base_6h ?? 0,
        doceHoras: rule?.base_12h ?? 0,
        semana: 0,
        mes: 0,
      };
    }
    return byId;
  }, [spaces, pricingRules]);

  // Prefer catalog/package unit prices when rules exist; otherwise allocate
  // price-preview totals so the table matches the bandeja.
  const useCatalogPricing = pricingRules.length > 0;
  const orderRows = useMemo(
    () => buildOrderTableRows(cartItems, useCatalogPricing ? pricingBySpaceId : {}),
    [cartItems, pricingBySpaceId, useCatalogPricing]
  );

  const subtotal = useMemo(() => {
    if (useCatalogPricing) {
      return orderRows.reduce((acc, row) => acc + row.total, 0);
    }
    return items.reduce((acc, item) => acc + (item.cotizacionCalculada ?? 0), 0);
  }, [useCatalogPricing, orderRows, items]);

  const grandTotal = Math.max(0, subtotal - discountAmount);

  // Clear stale discount if cart emptied.
  useEffect(() => {
    if (items.length === 0 && (appliedDiscountCode || discountAmount > 0)) {
      onDiscountApplied(null, 0);
      setDiscountMessage(null);
      setDiscountCodeInput('');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only react to cart emptiness
  }, [items.length]);

  const applyDiscountCode = async () => {
    const raw = discountCodeInput.trim();
    if (!raw) {
      setDiscountMessage('Ingresa un código de descuento.');
      return;
    }
    if (subtotal <= 0) {
      setDiscountMessage('Agrega al menos un horario antes de aplicar un código.');
      return;
    }
    setValidatingDiscount(true);
    setDiscountMessage(null);
    try {
      const resp = await apiClient.post<DiscountValidateResponse>(
        '/public/quote-requests/validate-discount',
        {
          code: raw,
          subtotal,
        }
      );
      const data = resp.data;
      if (!data.valid) {
        onDiscountApplied(null, 0);
        setDiscountMessage(
          DISCOUNT_REASON_MESSAGES[data.reason ?? ''] ?? 'No se pudo aplicar el código.'
        );
        return;
      }
      const amount = Number(data.discount_amount ?? 0);
      onDiscountApplied(data.code, Number.isFinite(amount) ? amount : 0);
      setDiscountMessage(`Código aplicado: ${data.code}`);
    } catch {
      onDiscountApplied(null, 0);
      setDiscountMessage('No se pudo validar el código en este momento.');
    } finally {
      setValidatingDiscount(false);
    }
  };

  const clearDiscountCode = () => {
    onDiscountApplied(null, 0);
    setDiscountMessage(null);
    setDiscountCodeInput('');
  };

  if (items.length === 0) return null;

  return (
    <section className="bg-white rounded-xl shadow border border-gray-200 overflow-hidden">
      <div className="px-4 sm:px-6 py-4 border-b border-gray-100 bg-gray-50/80">
        <h3 className="text-lg font-bold text-gray-900">Detalle de Espacios</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[640px]">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50 text-left text-gray-700">
              <th className="px-4 py-3 font-semibold">Espacio</th>
              <th className="px-4 py-3 font-semibold whitespace-nowrap">Tiempo</th>
              <th className="px-4 py-3 font-semibold text-right whitespace-nowrap">
                Precio unitario
              </th>
              <th className="px-4 py-3 font-semibold text-right whitespace-nowrap">Cantidad</th>
              <th className="px-4 py-3 font-semibold text-right whitespace-nowrap">Total</th>
            </tr>
          </thead>
          <tbody>
            {orderRows.map((row) => (
              <tr key={row.key} className="border-b border-gray-100 hover:bg-gray-50/50">
                <td className="px-4 py-3 text-gray-900 align-top">{row.espacio}</td>
                <td className="px-4 py-3 text-gray-700 whitespace-nowrap align-top">
                  {row.tiempoLabel}
                </td>
                <td className="px-4 py-3 text-right text-gray-800 align-top">
                  ${row.precioUnitario.toLocaleString('es-MX')}
                </td>
                <td className="px-4 py-3 text-right text-gray-800 align-top">
                  {formatCantidad(row.cantidad)}
                </td>
                <td className="px-4 py-3 text-right font-semibold text-gray-900 align-top">
                  ${row.total.toLocaleString('es-MX')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="px-4 sm:px-6 py-4 bg-gray-50/80 border-t border-gray-200 space-y-2 text-sm">
        <div className="pt-1 pb-2 border-b border-gray-200">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Código de descuento
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={discountCodeInput}
              onChange={(e) => setDiscountCodeInput(e.target.value.toUpperCase())}
              placeholder="Ej. BLOQUE10"
              className="flex-1 px-3 py-2 border border-gray-300 rounded-lg"
            />
            <button
              type="button"
              onClick={applyDiscountCode}
              disabled={validatingDiscount}
              className="px-4 py-2 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {validatingDiscount ? 'Validando...' : 'Aplicar'}
            </button>
            {appliedDiscountCode && (
              <button
                type="button"
                onClick={clearDiscountCode}
                className="px-4 py-2 rounded-lg bg-gray-200 text-gray-700 hover:bg-gray-300"
              >
                Quitar
              </button>
            )}
          </div>
          {discountMessage && (
            <p
              className={`mt-2 text-xs ${
                appliedDiscountCode ? 'text-emerald-700' : 'text-red-700'
              }`}
            >
              {discountMessage}
            </p>
          )}
        </div>
        <div className="flex justify-between gap-4">
          <span className="font-medium text-gray-700">Subtotal:</span>
          <span className="font-semibold text-gray-900">
            ${subtotal.toLocaleString('es-MX')}
          </span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="font-medium text-gray-700">Descuento:</span>
          <span className="text-gray-800">
            {discountAmount > 0 ? `-$${discountAmount.toLocaleString('es-MX')}` : '—'}
          </span>
        </div>
        <div className="flex justify-between gap-4 text-base pt-1 border-t border-gray-200">
          <span className="font-bold text-gray-900">Total:</span>
          <span className="font-bold text-blue-600 text-lg">
            ${grandTotal.toLocaleString('es-MX')}
          </span>
        </div>
      </div>
    </section>
  );
}
