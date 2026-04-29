'use client';

import { useMemo, useState } from 'react';
import useSWR from 'swr';
import { toast } from 'sonner';

import { CAN_ACCESS_PRICING_CONFIG, RoleGuard } from '@/features/auth';
import apiClient from '@/lib/http/apiClient';

interface Space {
  id: string;
  name: string;
}

interface PricingRule {
  id: string;
  space_id: string;
  base_6h: number;
  base_12h: number;
  extra_hour_rate: number;
  effective_from: string;
  effective_to?: string | null;
}

interface UmaRate {
  id: string;
  value: number;
  effective_date: string;
  created_at: string;
}

const fetcher = (url: string) => apiClient.get(url).then((r) => r.data);

function PricingContent() {
  const { data: spaces = [] } = useSWR<Space[]>('/spaces', fetcher);
  const { data: rules = [], mutate: mutateRules } = useSWR<PricingRule[]>('/pricing-rules', fetcher);
  const { data: umaRates = [], mutate: mutateUmaRates } = useSWR<UmaRate[]>('/uma-rates/', fetcher);

  const [selectedSpaceId, setSelectedSpaceId] = useState('');
  const currentRule = useMemo(
    () => rules.find((r) => r.space_id === selectedSpaceId),
    [rules, selectedSpaceId]
  );

  const [price6h, setPrice6h] = useState('');
  const [price12h, setPrice12h] = useState('');
  const [priceHour, setPriceHour] = useState('');

  const [umaValue, setUmaValue] = useState('');
  const [umaEffectiveDate, setUmaEffectiveDate] = useState(
    new Date().toLocaleDateString('en-CA', { timeZone: 'America/Mexico_City' })
  );
  const [saving, setSaving] = useState(false);

  const syncFormFromRule = (rule?: PricingRule) => {
    setPrice6h(rule ? String(rule.base_6h) : '');
    setPrice12h(rule ? String(rule.base_12h) : '');
    setPriceHour(rule ? String(rule.extra_hour_rate) : '');
  };

  const onSelectSpace = (spaceId: string) => {
    setSelectedSpaceId(spaceId);
    const rule = rules.find((r) => r.space_id === spaceId);
    syncFormFromRule(rule);
  };

  const savePricingRule = async () => {
    if (!selectedSpaceId) return toast.error('Selecciona un espacio');
    const basePayload = {
      base_6h: Number(price6h),
      base_12h: Number(price12h),
      extra_hour_rate: Number(priceHour),
    };
    if (
      Number.isNaN(basePayload.base_6h) ||
      Number.isNaN(basePayload.base_12h) ||
      Number.isNaN(basePayload.extra_hour_rate)
    ) {
      return toast.error('Ingresa valores numéricos válidos');
    }
    const effectiveFrom = new Date().toLocaleDateString('en-CA', {
      timeZone: 'America/Mexico_City',
    });
    setSaving(true);
    try {
      if (currentRule) {
        await apiClient.put(`/pricing-rules/${selectedSpaceId}`, basePayload);
      } else {
        await apiClient.post('/pricing-rules', {
          space_id: selectedSpaceId,
          ...basePayload,
          effective_from: effectiveFrom,
        });
      }
      await mutateRules();
      toast.success('Cuotas guardadas');
    } catch (e: unknown) {
      const detail =
        e && typeof e === 'object' && 'response' in e
          ? (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      toast.error(detail || 'No se pudo guardar la cuota');
    } finally {
      setSaving(false);
    }
  };

  const saveUmaRate = async () => {
    const payload = {
      value: Number(umaValue),
      effective_date: umaEffectiveDate,
    };
    if (Number.isNaN(payload.value) || payload.value <= 0) return toast.error('UMA inválida');
    setSaving(true);
    try {
      await apiClient.post('/uma-rates/', payload);
      setUmaValue('');
      await mutateUmaRates();
      toast.success('UMA registrada');
    } catch (e: unknown) {
      const detail =
        e && typeof e === 'object' && 'response' in e
          ? (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      toast.error(detail || 'No se pudo registrar UMA');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Configuración de Cuotas</h1>
        <p className="text-sm text-gray-600 mt-1">Administra tarifas por espacio (MXN) y valores UMA por sede.</p>
      </div>

      <section className="bg-white rounded-xl border border-gray-200 p-4 space-y-4">
        <h2 className="font-semibold text-gray-900">Cuotas por espacio (MXN)</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <label className="text-sm md:col-span-2">
            <span className="text-gray-600">Espacio</span>
            <select
              value={selectedSpaceId}
              onChange={(e) => onSelectSpace(e.target.value)}
              className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2"
            >
              <option value="">Selecciona...</option>
              {spaces.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="text-gray-600">6 horas</span>
            <input
              type="number"
              step="0.01"
              value={price6h}
              onChange={(e) => setPrice6h(e.target.value)}
              className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2"
            />
          </label>
          <label className="text-sm">
            <span className="text-gray-600">12 horas</span>
            <input
              type="number"
              step="0.01"
              value={price12h}
              onChange={(e) => setPrice12h(e.target.value)}
              className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2"
            />
          </label>
          <label className="text-sm">
            <span className="text-gray-600">Por hora</span>
            <input
              type="number"
              step="0.01"
              value={priceHour}
              onChange={(e) => setPriceHour(e.target.value)}
              className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2"
            />
          </label>
        </div>
        <button
          type="button"
          onClick={savePricingRule}
          disabled={saving}
          className="px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
        >
          Guardar cuotas MXN
        </button>
      </section>

      <section className="bg-white rounded-xl border border-gray-200 p-4 space-y-4">
        <h2 className="font-semibold text-gray-900">Valores UMA (append-only)</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-w-xl">
          <label className="text-sm">
            <span className="text-gray-600">Valor UMA</span>
            <input
              type="number"
              step="0.0001"
              value={umaValue}
              onChange={(e) => setUmaValue(e.target.value)}
              className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2"
            />
          </label>
          <label className="text-sm">
            <span className="text-gray-600">Fecha efectiva (vigencia)</span>
            <input
              type="date"
              value={umaEffectiveDate}
              onChange={(e) => setUmaEffectiveDate(e.target.value)}
              className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2"
            />
          </label>
        </div>
        <button
          type="button"
          onClick={saveUmaRate}
          disabled={saving}
          className="px-4 py-2 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          Registrar UMA
        </button>

        <div className="overflow-x-auto pt-2">
          <table className="w-full text-sm min-w-[520px]">
            <thead>
              <tr className="text-left text-gray-700 border-b border-gray-200">
                <th className="py-2 font-semibold">Fecha efectiva</th>
                <th className="py-2 font-semibold">Valor</th>
                <th className="py-2 font-semibold">Creado</th>
              </tr>
            </thead>
            <tbody>
              {umaRates.map((r) => (
                <tr key={r.id} className="border-b border-gray-100">
                  <td className="py-2">{r.effective_date}</td>
                  <td className="py-2">{Number(r.value).toLocaleString('es-MX', { minimumFractionDigits: 4, maximumFractionDigits: 4 })}</td>
                  <td className="py-2 text-gray-600">{new Date(r.created_at).toLocaleString('es-MX')}</td>
                </tr>
              ))}
              {umaRates.length === 0 && (
                <tr>
                  <td className="py-3 text-gray-500" colSpan={3}>
                    Sin registros UMA.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

export default function PricingPage() {
  return (
    <RoleGuard allowedRoles={CAN_ACCESS_PRICING_CONFIG}>
      <PricingContent />
    </RoleGuard>
  );
}

