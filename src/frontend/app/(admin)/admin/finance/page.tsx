'use client';

/**
 * Módulo Finanzas: conciliación (aprobar/rechazar pagos), estado CFDIs, notas de crédito.
 * Requiere rol FINANCE o SUPERADMIN. SoD: doble confirmación antes de aprobar.
 */

import { useState } from 'react';
import useSWR from 'swr';
import { toast } from 'sonner';
import { CAN_ACCESS_FINANCE, RoleGuard } from '@/features/auth';
import apiClient from '@/lib/http/apiClient';
import { formatDateOnlyLocal, todayMexico } from '@/lib/dateUtils';

interface Reservation {
  id: string;
  tenant_id: string;
  user_id: string;
  space_id: string;
  fecha: string;
  hora_inicio: string;
  hora_fin: string;
  status: string;
  created_at: string;
  updated_at: string;
}

interface CreditBalance {
  id: string;
  tenant_id: string;
  cfdi_uuid: string;
  monto_original: number;
  saldo_restante: number;
  reservation_origen_id: string | null;
  aplicado_a_reservation_id: string | null;
  created_at: string;
}

interface Voucher {
  id: string;
  reservation_id: string;
  file_url: string;
  file_type: string;
  uploaded_at: string;
}

const fetcher = (url: string) => apiClient.get(url).then((r) => r.data);

function FinanceContent() {
  const [confirmModal, setConfirmModal] = useState<{
    type: 'approve' | 'reject';
    reservation: Reservation;
  } | null>(null);
  const [rejectMotivo, setRejectMotivo] = useState('');
  const [loading, setLoading] = useState(false);
  const [voucherReservationId, setVoucherReservationId] = useState<string | null>(null);
  const [applyModal, setApplyModal] = useState<{
    credit: CreditBalance;
    reservationId: string;
    monto: number;
  } | null>(null);

  const { data: underReview = [], mutate: mutateReservations } = useSWR<Reservation[]>(
    '/reservations?status=PAYMENT_UNDER_REVIEW',
    fetcher
  );
  const { data: credits = [], mutate: mutateCredits } = useSWR<CreditBalance[]>(
    '/finance/credits',
    fetcher
  );
  const { data: allReservationsForCredit = [] } = useSWR<Reservation[]>(
    applyModal ? '/reservations' : null,
    fetcher
  );
  const eligibleReservations = allReservationsForCredit.filter((r) =>
    ['CONFIRMED', 'AWAITING_PAYMENT'].includes(r.status)
  );
  const { data: vouchers = [] } = useSWR<Voucher[]>(
    voucherReservationId ? `/reservations/${voucherReservationId}/vouchers` : null,
    fetcher
  );

  const handleConfirm = async () => {
    if (!confirmModal) return;
    setLoading(true);
    try {
      if (confirmModal.type === 'approve') {
        await apiClient.post(`/reservations/${confirmModal.reservation.id}/confirm`);
        toast.success('Pago aprobado');
      } else {
        await apiClient.post(`/reservations/${confirmModal.reservation.id}/reject`, {
          motivo: rejectMotivo || undefined,
        });
        toast.success('Pago rechazado');
      }
      setConfirmModal(null);
      setRejectMotivo('');
      mutateReservations();
    } catch (err: unknown) {
      const detail = err && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : 'Error';
      toast.error(String(detail));
    } finally {
      setLoading(false);
    }
  };

  const handleApplyCredit = async () => {
    if (!applyModal) return;
    setLoading(true);
    try {
      await apiClient.post(`/finance/credits/${applyModal.credit.id}/apply`, {
        reservation_id: applyModal.reservationId,
        monto_a_aplicar: applyModal.monto,
      });
      toast.success(`Crédito aplicado: $${applyModal.monto.toFixed(2)}`);
      setApplyModal(null);
      mutateCredits();
      mutateReservations();
    } catch (err: unknown) {
      const detail = err && typeof err === 'object' && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : 'Error al aplicar crédito';
      toast.error(String(detail));
    } finally {
      setLoading(false);
    }
  };

  const exportMonthly = () => {
    const rows = underReview.map((r) => ({
      id: r.id,
      fecha: r.fecha,
      hora: `${r.hora_inicio}-${r.hora_fin}`,
      status: r.status,
    }));
    const csv = [
      'id,fecha,hora,status',
      ...rows.map((r) => `${r.id},${r.fecha},${r.hora},${r.status}`),
    ].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `reservas-revision-${todayMexico()}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
    toast.success('Exportado');
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Finanzas</h1>
        <button
          type="button"
          onClick={exportMonthly}
          className="px-4 py-2 rounded-lg border border-gray-300 text-gray-700 font-medium hover:bg-gray-50"
        >
          Exportar reporte (CSV)
        </button>
      </div>

      <section>
        <h2 className="text-lg font-semibold text-gray-800 mb-2">Reservas en revisión de pago</h2>
        <div className="border border-gray-200 rounded-lg overflow-hidden">
          <table className="w-full text-sm text-left">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-4 py-2 font-medium text-gray-700">ID</th>
                <th className="px-4 py-2 font-medium text-gray-700">Fecha</th>
                <th className="px-4 py-2 font-medium text-gray-700">Hora</th>
                <th className="px-4 py-2 font-medium text-gray-700">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {underReview.map((r) => (
                <tr key={r.id} className="border-b border-gray-100 hover:bg-gray-50/50">
                  <td className="px-4 py-2 font-mono text-xs">{r.id.slice(0, 8)}</td>
                  <td className="px-4 py-2">{formatDateOnlyLocal(r.fecha)}</td>
                  <td className="px-4 py-2">{r.hora_inicio} - {r.hora_fin}</td>
                  <td className="px-4 py-2 space-x-2">
                    <button
                      type="button"
                      onClick={() => setVoucherReservationId(
                        voucherReservationId === r.id ? null : r.id
                      )}
                      className="px-2 py-1 rounded bg-gray-100 text-gray-700 text-xs font-medium hover:bg-gray-200 border border-gray-300"
                      aria-label={`Ver comprobante de reserva ${r.id.slice(0, 8)}`}
                    >
                      {voucherReservationId === r.id ? 'Ocultar' : 'Ver comprobante'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmModal({ type: 'approve', reservation: r })}
                      className="px-2 py-1 rounded bg-green-600 text-white text-xs font-medium hover:bg-green-700"
                      aria-label={`Aprobar pago de reserva ${r.id.slice(0, 8)}`}
                    >
                      Aprobar
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmModal({ type: 'reject', reservation: r })}
                      className="px-2 py-1 rounded bg-red-600 text-white text-xs font-medium hover:bg-red-700"
                      aria-label={`Rechazar pago de reserva ${r.id.slice(0, 8)}`}
                    >
                      Rechazar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {underReview.length === 0 && (
            <div className="p-4 text-center text-gray-500 text-sm">
              No hay reservas en revisión
            </div>
          )}
        </div>
        {voucherReservationId && (
          <div className="mt-3 p-4 bg-gray-50 border border-gray-200 rounded-lg">
            <h3 className="text-sm font-semibold text-gray-800 mb-2">
              Comprobantes de reserva {voucherReservationId.slice(0, 8)}
            </h3>
            {vouchers.length === 0 ? (
              <p className="text-sm text-gray-500">No se encontraron comprobantes.</p>
            ) : (
              <div className="space-y-2">
                {vouchers.map((v) => {
                  const isImage = v.file_type?.startsWith('image/');
                  const downloadUrl = `/reservations/${v.reservation_id}/vouchers/${v.id}/download`;
                  return (
                    <div key={v.id} className="flex items-center gap-3 p-2 bg-white rounded border border-gray-100">
                      <div className="flex-1">
                        <div className="text-sm font-medium text-gray-900">{v.file_url}</div>
                        <div className="text-xs text-gray-500">
                          {new Date(v.uploaded_at).toLocaleString('es-MX', { dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Mexico_City' })}
                          {' · '}
                          {isImage ? 'Imagen' : 'PDF'}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={async () => {
                          try {
                            const res = await apiClient.get(downloadUrl, { responseType: 'blob' });
                            const blob = new Blob([res.data], { type: v.file_type });
                            const url = URL.createObjectURL(blob);
                            if (isImage) {
                              window.open(url, '_blank');
                            } else {
                              const a = document.createElement('a');
                              a.href = url;
                              a.download = v.file_url;
                              a.click();
                              URL.revokeObjectURL(url);
                            }
                          } catch (err: unknown) {
                            const ax = err as { response?: { status?: number; data?: Blob | { detail?: string } } };
                            let msg = 'No se pudo descargar el comprobante.';
                            if (ax.response?.data) {
                              const data = ax.response.data;
                              if (data instanceof Blob && data.type?.includes('application/json')) {
                                try {
                                  const text = await data.text();
                                  const obj = JSON.parse(text) as { detail?: string };
                                  msg = obj.detail ?? msg;
                                } catch {
                                  msg = ax.response.status === 404
                                    ? 'Comprobante o archivo no encontrado. Si el comprobante se subió antes de usar el volumen de datos, vuelva a subirlo.'
                                    : msg;
                                }
                              } else if (typeof data === 'object' && data && 'detail' in data) {
                                msg = String((data as { detail?: string }).detail);
                              } else if (ax.response.status === 404) {
                                msg = 'Comprobante o archivo no encontrado.';
                              }
                            }
                            toast.error(msg);
                          }
                        }}
                        className="px-3 py-1 rounded bg-blue-600 text-white text-xs font-medium hover:bg-blue-700"
                      >
                        {isImage ? 'Ver imagen' : 'Descargar PDF'}
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </section>

      <section>
        <h2 className="text-lg font-semibold text-gray-800 mb-2">Notas de crédito (saldos a favor)</h2>
        <div className="border border-gray-200 rounded-lg overflow-hidden">
          <table className="w-full text-sm text-left">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-4 py-2 font-medium text-gray-700">ID</th>
                <th className="px-4 py-2 font-medium text-gray-700">Monto original</th>
                <th className="px-4 py-2 font-medium text-gray-700">Saldo restante</th>
                <th className="px-4 py-2 font-medium text-gray-700">Aplicado a reserva</th>
                <th className="px-4 py-2 font-medium text-gray-700">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {credits.map((c) => (
                <tr key={c.id} className="border-b border-gray-100">
                  <td className="px-4 py-2 font-mono text-xs">{c.id.slice(0, 8)}</td>
                  <td className="px-4 py-2">${c.monto_original.toFixed(2)}</td>
                  <td className="px-4 py-2">${c.saldo_restante.toFixed(2)}</td>
                  <td className="px-4 py-2">
                    {c.aplicado_a_reservation_id
                      ? c.aplicado_a_reservation_id.slice(0, 8)
                      : '—'}
                  </td>
                  <td className="px-4 py-2">
                    {c.saldo_restante > 0 && !c.aplicado_a_reservation_id ? (
                      <button
                        type="button"
                        onClick={() => setApplyModal({ credit: c, reservationId: '', monto: c.saldo_restante })}
                        className="px-3 py-1 rounded bg-blue-600 text-white text-xs font-medium hover:bg-blue-700"
                      >
                        Aplicar
                      </button>
                    ) : (
                      <span className="text-gray-400 text-xs">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {credits.length === 0 && (
            <div className="p-4 text-center text-gray-500 text-sm">
              No hay créditos con saldo disponible
            </div>
          )}
        </div>
      </section>

      {confirmModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6">
            <h3 className="text-lg font-bold text-gray-900 mb-2">
              {confirmModal.type === 'approve' ? 'Confirmar aprobación de pago' : 'Confirmar rechazo de pago'}
            </h3>
            <p className="text-sm text-gray-600 mb-4">
              Reserva <code className="bg-gray-100 px-1 rounded">{confirmModal.reservation.id.slice(0, 8)}</code>{' '}
              — {formatDateOnlyLocal(confirmModal.reservation.fecha)} {confirmModal.reservation.hora_inicio}-{confirmModal.reservation.hora_fin}
            </p>
            {confirmModal.type === 'reject' && (
              <label className="block mb-4">
                <span className="text-sm font-medium text-gray-700">Motivo (opcional)</span>
                <input
                  type="text"
                  value={rejectMotivo}
                  onChange={(e) => setRejectMotivo(e.target.value)}
                  className="mt-1 w-full border border-gray-300 rounded px-3 py-2 text-sm"
                  placeholder="Motivo del rechazo"
                />
              </label>
            )}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setConfirmModal(null);
                  setRejectMotivo('');
                }}
                className="px-4 py-2 rounded border border-gray-300 text-gray-700 font-medium hover:bg-gray-50"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={handleConfirm}
                disabled={loading}
                className={`px-4 py-2 rounded font-medium text-white disabled:opacity-50 ${
                  confirmModal.type === 'approve'
                    ? 'bg-green-600 hover:bg-green-700'
                    : 'bg-red-600 hover:bg-red-700'
                }`}
              >
                {loading ? 'Procesando...' : confirmModal.type === 'approve' ? 'Aprobar' : 'Rechazar'}
              </button>
            </div>
          </div>
        </div>
      )}

      {applyModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6">
            <h3 className="text-lg font-bold text-gray-900 mb-2">
              Aplicar crédito a reserva
            </h3>
            <p className="text-sm text-gray-600 mb-4">
              Crédito: <code className="bg-gray-100 px-1 rounded">{applyModal.credit.id.slice(0, 8)}</code><br />
              Saldo disponible: <strong>${applyModal.credit.saldo_restante.toFixed(2)}</strong>
            </p>

            {/* Selector de reserva */}
            <label className="block mb-3">
              <span className="text-sm font-medium text-gray-700">Reserva a acreditar</span>
              <select
                value={applyModal.reservationId}
                onChange={(e) => setApplyModal({ ...applyModal, reservationId: e.target.value })}
                className="mt-1 w-full border border-gray-300 rounded px-3 py-2 text-sm"
              >
                <option value="">Seleccionar reserva...</option>
                {eligibleReservations.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.id.slice(0, 8)} — {formatDateOnlyLocal(r.fecha)} {r.hora_inicio}-{r.hora_fin}
                  </option>
                ))}
              </select>
            </label>

            {/* Input de monto */}
            <label className="block mb-4">
              <span className="text-sm font-medium text-gray-700">Monto a aplicar</span>
              <input
                type="number"
                step="0.01"
                min="0.01"
                max={applyModal.credit.saldo_restante}
                value={applyModal.monto}
                onChange={(e) => setApplyModal({ ...applyModal, monto: Number(e.target.value) })}
                className="mt-1 w-full border border-gray-300 rounded px-3 py-2 text-sm"
                placeholder="0.00"
              />
            </label>

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setApplyModal(null)}
                className="px-4 py-2 rounded border border-gray-300 text-gray-700 font-medium hover:bg-gray-50"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={handleApplyCredit}
                disabled={!applyModal.reservationId || applyModal.monto <= 0 || loading}
                className="px-4 py-2 rounded font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50"
              >
                {loading ? 'Aplicando...' : 'Aplicar crédito'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function FinancePage() {
  return (
    <RoleGuard allowedRoles={CAN_ACCESS_FINANCE}>
      <FinanceContent />
    </RoleGuard>
  );
}
