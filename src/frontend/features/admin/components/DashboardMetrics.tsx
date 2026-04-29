'use client';

import { useState } from 'react';
import useSWR from 'swr';
import apiClient from '@/lib/http/apiClient';
import { Activity, Percent, ShieldCheck, CheckCircle2 } from 'lucide-react';

interface Metrics {
  kr23: { total_discounts: number; justified_discounts: number; justification_rate: number };
  kr24: { total_snapshots: number; invariant_snapshots: number; invariance_rate: number };
  kr25: { total_hybrid_quotes: number; accurate_hybrid_quotes: number; precision_rate: number };
  kr27: { total_ready_transitions: number; transitions_with_checklist: number; compliance_rate: number };
}

const fetcher = (url: string) => apiClient.get(url).then((res) => res.data);

export default function DashboardMetrics() {
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const params = new URLSearchParams();
  if (dateFrom) params.append('start_date', dateFrom);
  if (dateTo) params.append('end_date', dateTo);
  const query = params.toString();
  const url = `/analytics/dashboard${query ? '?' + query : ''}`;

  const { data: metrics, error, isLoading } = useSWR<Metrics>(url, fetcher, {
    refreshInterval: 60000,
  });

  return (
    <div className="mt-8 space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <h2 className="text-lg font-semibold text-gray-900">Métricas y Salud del Sistema (KPIs)</h2>
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600">Periodo:</label>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="border border-gray-300 rounded-lg px-2 py-1 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
          />
          <span className="text-sm text-gray-400">a</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="border border-gray-300 rounded-lg px-2 py-1 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
          />
        </div>
      </div>

      {isLoading ? (
        <div className="animate-pulse bg-gray-100 rounded-xl h-32 w-full mt-4"></div>
      ) : error || !metrics ? (
        <div className="mt-4 p-4 bg-red-50 text-red-600 rounded-xl text-sm">
          Error al cargar los KPIs.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mt-4">
          {/* KR-23: O-03 */}
          <div className="bg-white p-4 rounded-xl border border-gray-200 shadow-sm flex flex-col">
            <div className="flex items-center gap-2 mb-2">
              <Percent className="w-5 h-5 text-blue-600" />
              <h3 className="font-medium text-gray-800 text-sm">KR-23 (O-03)</h3>
            </div>
            <p className="text-xs text-gray-500 mb-3">Justificación de descuentos</p>
            <div className="mt-auto">
              <p className="text-2xl font-bold text-gray-900">{metrics.kr23.justification_rate.toFixed(1)}%</p>
              <p className="text-xs text-gray-600 mt-1">
                {metrics.kr23.justified_discounts} / {metrics.kr23.total_discounts} justificados
              </p>
              <div className="w-full bg-gray-200 rounded-full h-1.5 mt-2">
                <div 
                  className="bg-blue-600 h-1.5 rounded-full" 
                  style={{ width: `${metrics.kr23.justification_rate}%` }}
                ></div>
              </div>
            </div>
          </div>

          {/* KR-24: O-04 */}
          <div className="bg-white p-4 rounded-xl border border-gray-200 shadow-sm flex flex-col">
            <div className="flex items-center gap-2 mb-2">
              <ShieldCheck className="w-5 h-5 text-green-600" />
              <h3 className="font-medium text-gray-800 text-sm">KR-24 (O-04)</h3>
            </div>
            <p className="text-xs text-gray-500 mb-3">Invariancia MXN vs snapshot</p>
            <div className="mt-auto">
              <p className="text-2xl font-bold text-gray-900">{metrics.kr24.invariance_rate.toFixed(1)}%</p>
              <p className="text-xs text-gray-600 mt-1">
                {metrics.kr24.invariant_snapshots} / {metrics.kr24.total_snapshots} invariantes
              </p>
              <div className="w-full bg-gray-200 rounded-full h-1.5 mt-2">
                <div 
                  className="bg-green-600 h-1.5 rounded-full" 
                  style={{ width: `${metrics.kr24.invariance_rate}%` }}
                ></div>
              </div>
            </div>
          </div>

          {/* KR-25: O-04 */}
          <div className="bg-white p-4 rounded-xl border border-gray-200 shadow-sm flex flex-col">
            <div className="flex items-center gap-2 mb-2">
              <Activity className="w-5 h-5 text-purple-600" />
              <h3 className="font-medium text-gray-800 text-sm">KR-25 (O-04)</h3>
            </div>
            <p className="text-xs text-gray-500 mb-3">Precisión pricing híbrido</p>
            <div className="mt-auto">
              <p className="text-2xl font-bold text-gray-900">{metrics.kr25.precision_rate.toFixed(1)}%</p>
              <p className="text-xs text-gray-600 mt-1">
                {metrics.kr25.accurate_hybrid_quotes} / {metrics.kr25.total_hybrid_quotes} precisas
              </p>
              <div className="w-full bg-gray-200 rounded-full h-1.5 mt-2">
                <div 
                  className="bg-purple-600 h-1.5 rounded-full" 
                  style={{ width: `${metrics.kr25.precision_rate}%` }}
                ></div>
              </div>
            </div>
          </div>

          {/* KR-27: O-05 */}
          <div className="bg-white p-4 rounded-xl border border-gray-200 shadow-sm flex flex-col">
            <div className="flex items-center gap-2 mb-2">
              <CheckCircle2 className="w-5 h-5 text-amber-600" />
              <h3 className="font-medium text-gray-800 text-sm">KR-27 (O-05)</h3>
            </div>
            <p className="text-xs text-gray-500 mb-3">Gating de READY por checklist</p>
            <div className="mt-auto">
              <p className="text-2xl font-bold text-gray-900">{metrics.kr27.compliance_rate.toFixed(1)}%</p>
              <p className="text-xs text-gray-600 mt-1">
                {metrics.kr27.transitions_with_checklist} / {metrics.kr27.total_ready_transitions} con checklist
              </p>
              <div className="w-full bg-gray-200 rounded-full h-1.5 mt-2">
                <div 
                  className="bg-amber-600 h-1.5 rounded-full" 
                  style={{ width: `${metrics.kr27.compliance_rate}%` }}
                ></div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tabla detallada / Series según el requerimiento */}
      {!isLoading && !error && metrics && (
        <div className="mt-8 bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <div className="p-4 border-b border-gray-200 bg-gray-50">
            <h3 className="font-medium text-gray-800">Definición y Estado de Salud</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left text-gray-600">
              <thead className="bg-gray-50 text-gray-700 font-semibold border-b">
                <tr>
                  <th className="px-4 py-3">KPI</th>
                  <th className="px-4 py-3">Objetivo</th>
                  <th className="px-4 py-3">Definición</th>
                  <th className="px-4 py-3">Valor Actual</th>
                  <th className="px-4 py-3">Estado</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                <tr className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-800">KR-23</td>
                  <td className="px-4 py-3 text-xs bg-blue-50 text-blue-700 font-medium rounded text-center my-1 mx-2 block w-fit px-2">O-03</td>
                  <td className="px-4 py-3 text-xs">Cumplimiento de justificación de descuentos aplicados en cotizaciones.</td>
                  <td className="px-4 py-3 font-semibold">{metrics.kr23.justification_rate.toFixed(1)}%</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 rounded text-xs font-medium ${metrics.kr23.justification_rate >= 90 ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'}`}>
                      {metrics.kr23.justification_rate >= 90 ? 'Saludable' : 'Alerta'}
                    </span>
                  </td>
                </tr>
                <tr className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-800">KR-24</td>
                  <td className="px-4 py-3 text-xs bg-green-50 text-green-700 font-medium rounded text-center my-1 mx-2 block w-fit px-2">O-04</td>
                  <td className="px-4 py-3 text-xs">Invariancia de total MXN vs el snapshot inicial al confirmar reserva.</td>
                  <td className="px-4 py-3 font-semibold">{metrics.kr24.invariance_rate.toFixed(1)}%</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 rounded text-xs font-medium ${metrics.kr24.invariance_rate >= 99 ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                      {metrics.kr24.invariance_rate >= 99 ? 'Saludable' : 'Peligro'}
                    </span>
                  </td>
                </tr>
                <tr className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-800">KR-25</td>
                  <td className="px-4 py-3 text-xs bg-purple-50 text-purple-700 font-medium rounded text-center my-1 mx-2 block w-fit px-2">O-04</td>
                  <td className="px-4 py-3 text-xs">Precisión del modelo de pricing híbrido vs cotizaciones finales.</td>
                  <td className="px-4 py-3 font-semibold">{metrics.kr25.precision_rate.toFixed(1)}%</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 rounded text-xs font-medium ${metrics.kr25.precision_rate >= 80 ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'}`}>
                      {metrics.kr25.precision_rate >= 80 ? 'Saludable' : 'Alerta'}
                    </span>
                  </td>
                </tr>
                <tr className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-800">KR-27</td>
                  <td className="px-4 py-3 text-xs bg-amber-50 text-amber-700 font-medium rounded text-center my-1 mx-2 block w-fit px-2">O-05</td>
                  <td className="px-4 py-3 text-xs">Transiciones a READY bloqueadas (gating) por falta de checklist de montaje.</td>
                  <td className="px-4 py-3 font-semibold">{metrics.kr27.compliance_rate.toFixed(1)}%</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 rounded text-xs font-medium ${metrics.kr27.compliance_rate >= 95 ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                      {metrics.kr27.compliance_rate >= 95 ? 'Saludable' : 'Peligro'}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
