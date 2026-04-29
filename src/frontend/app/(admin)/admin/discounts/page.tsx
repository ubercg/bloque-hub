'use client';

import { useMemo, useState } from 'react';
import useSWR from 'swr';

import { CAN_ACCESS_DISCOUNT_CONFIG, RoleGuard } from '@/features/auth';
import apiClient from '@/lib/http/apiClient';

interface DiscountCodeApi {
  id: string;
  code: string;
  discount_type: 'PERCENT' | 'FIXED';
  discount_value: string | number;
  min_subtotal?: string | number | null;
  max_uses?: number | null;
  used_count: number;
  active: boolean;
  expires_at?: string | null;
  single_use_per_user: boolean;
  status: string;
}

interface DiscountUsageApi {
  id: string;
  group_event_id?: string | null;
  reservation_id?: string | null;
  used_by_user_id: string;
  applied_subtotal: string | number;
  applied_discount_amount: string | number;
  applied_total: string | number;
  used_at: string;
}

const fetcher = (url: string) => apiClient.get(url).then((r) => r.data);

function DiscountsContent() {
  const { data: codes = [], mutate } = useSWR<DiscountCodeApi[]>('/admin/discount-codes', fetcher);
  const [selectedCodeId, setSelectedCodeId] = useState<string | null>(null);
  const { data: usages = [] } = useSWR<DiscountUsageApi[]>(
    selectedCodeId ? `/admin/discount-codes/${selectedCodeId}/usages` : null,
    fetcher
  );

  const [form, setForm] = useState({
    code: '',
    discount_type: 'PERCENT' as 'PERCENT' | 'FIXED',
    discount_value: '',
    min_subtotal: '',
    max_uses: '',
    expires_at: '',
    active: true,
    single_use_per_user: false,
  });
  const [saving, setSaving] = useState(false);

  const selectedCode = useMemo(
    () => codes.find((c) => c.id === selectedCodeId) ?? null,
    [codes, selectedCodeId]
  );

  const saveCode = async () => {
    if (!form.code.trim()) return;
    setSaving(true);
    try {
      const payload = {
        code: form.code.trim().toUpperCase(),
        discount_type: form.discount_type,
        discount_value: Number(form.discount_value),
        min_subtotal: form.min_subtotal ? Number(form.min_subtotal) : null,
        max_uses: form.max_uses ? Number(form.max_uses) : null,
        expires_at: form.expires_at ? new Date(form.expires_at).toISOString() : null,
        active: form.active,
        single_use_per_user: form.single_use_per_user,
      };
      await apiClient.post('/admin/discount-codes', payload);
      await mutate();
      setForm({
        code: '',
        discount_type: 'PERCENT',
        discount_value: '',
        min_subtotal: '',
        max_uses: '',
        expires_at: '',
        active: true,
        single_use_per_user: false,
      });
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (code: DiscountCodeApi) => {
    await apiClient.patch(`/admin/discount-codes/${code.id}`, { active: !code.active });
    await mutate();
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Códigos de descuento</h1>
        <p className="text-sm text-gray-600">Alta, control de uso y auditoría de descuentos por código.</p>
      </div>

      <section className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
        <h2 className="font-semibold text-gray-900">Crear código</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <input
            placeholder="Código"
            value={form.code}
            onChange={(e) => setForm((prev) => ({ ...prev, code: e.target.value.toUpperCase() }))}
            className="border border-gray-300 rounded-lg px-3 py-2"
          />
          <select
            value={form.discount_type}
            onChange={(e) => setForm((prev) => ({ ...prev, discount_type: e.target.value as 'PERCENT' | 'FIXED' }))}
            className="border border-gray-300 rounded-lg px-3 py-2"
          >
            <option value="PERCENT">Porcentaje</option>
            <option value="FIXED">Monto fijo</option>
          </select>
          <input
            type="number"
            step="0.01"
            placeholder="Valor"
            value={form.discount_value}
            onChange={(e) => setForm((prev) => ({ ...prev, discount_value: e.target.value }))}
            className="border border-gray-300 rounded-lg px-3 py-2"
          />
          <input
            type="number"
            step="0.01"
            placeholder="Mínimo de compra"
            value={form.min_subtotal}
            onChange={(e) => setForm((prev) => ({ ...prev, min_subtotal: e.target.value }))}
            className="border border-gray-300 rounded-lg px-3 py-2"
          />
          <input
            type="number"
            placeholder="Usos máximos"
            value={form.max_uses}
            onChange={(e) => setForm((prev) => ({ ...prev, max_uses: e.target.value }))}
            className="border border-gray-300 rounded-lg px-3 py-2"
          />
          <input
            type="datetime-local"
            value={form.expires_at}
            onChange={(e) => setForm((prev) => ({ ...prev, expires_at: e.target.value }))}
            className="border border-gray-300 rounded-lg px-3 py-2"
          />
          <label className="inline-flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={form.active}
              onChange={(e) => setForm((prev) => ({ ...prev, active: e.target.checked }))}
            />
            Activo
          </label>
          <label className="inline-flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={form.single_use_per_user}
              onChange={(e) => setForm((prev) => ({ ...prev, single_use_per_user: e.target.checked }))}
            />
            Único por usuario
          </label>
        </div>
        <button
          type="button"
          onClick={saveCode}
          disabled={saving}
          className="px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {saving ? 'Guardando...' : 'Crear código'}
        </button>
      </section>

      <section className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
        <h2 className="font-semibold text-gray-900">Listado</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[960px]">
            <thead>
              <tr className="text-left border-b border-gray-200">
                <th className="py-2">Código</th>
                <th className="py-2">Tipo</th>
                <th className="py-2">Valor</th>
                <th className="py-2">Usos</th>
                <th className="py-2">Estado</th>
                <th className="py-2">Expira</th>
                <th className="py-2">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {codes.map((c) => (
                <tr key={c.id} className="border-b border-gray-100">
                  <td className="py-2 font-semibold">{c.code}</td>
                  <td className="py-2">{c.discount_type === 'PERCENT' ? 'Porcentaje' : 'Monto fijo'}</td>
                  <td className="py-2">{Number(c.discount_value).toLocaleString('es-MX')}</td>
                  <td className="py-2">{c.used_count}/{c.max_uses ?? '∞'}</td>
                  <td className="py-2">{c.status}</td>
                  <td className="py-2">{c.expires_at ? new Date(c.expires_at).toLocaleString('es-MX') : '—'}</td>
                  <td className="py-2 space-x-2">
                    <button
                      type="button"
                      onClick={() => setSelectedCodeId(c.id)}
                      className="px-2 py-1 rounded bg-gray-100 hover:bg-gray-200"
                    >
                      Ver usos
                    </button>
                    <button
                      type="button"
                      onClick={() => toggleActive(c)}
                      className="px-2 py-1 rounded bg-amber-100 hover:bg-amber-200"
                    >
                      {c.active ? 'Desactivar' : 'Activar'}
                    </button>
                  </td>
                </tr>
              ))}
              {codes.length === 0 && (
                <tr><td colSpan={7} className="py-4 text-gray-500">Sin códigos registrados.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
        <h2 className="font-semibold text-gray-900">
          Auditoría de uso {selectedCode ? `(${selectedCode.code})` : ''}
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[920px]">
            <thead>
              <tr className="text-left border-b border-gray-200">
                <th className="py-2">Fecha</th>
                <th className="py-2">Usuario</th>
                <th className="py-2">Evento</th>
                <th className="py-2">Reservación</th>
                <th className="py-2">Subtotal</th>
                <th className="py-2">Descuento</th>
                <th className="py-2">Total</th>
              </tr>
            </thead>
            <tbody>
              {usages.map((u) => (
                <tr key={u.id} className="border-b border-gray-100">
                  <td className="py-2">{new Date(u.used_at).toLocaleString('es-MX')}</td>
                  <td className="py-2">{u.used_by_user_id}</td>
                  <td className="py-2">{u.group_event_id ?? '—'}</td>
                  <td className="py-2">{u.reservation_id ?? '—'}</td>
                  <td className="py-2">${Number(u.applied_subtotal).toLocaleString('es-MX')}</td>
                  <td className="py-2">-${Number(u.applied_discount_amount).toLocaleString('es-MX')}</td>
                  <td className="py-2">${Number(u.applied_total).toLocaleString('es-MX')}</td>
                </tr>
              ))}
              {(!selectedCodeId || usages.length === 0) && (
                <tr><td colSpan={7} className="py-4 text-gray-500">Selecciona un código para ver sus usos.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

export default function AdminDiscountsPage() {
  return (
    <RoleGuard allowedRoles={CAN_ACCESS_DISCOUNT_CONFIG}>
      <DiscountsContent />
    </RoleGuard>
  );
}
