'use client';

/**
 * Wizard Step 4 — Servicios y montaje (REQ-012 §4, RN-011). `servicios_apoyo`
 * is a best-effort catalog fetch (no dedicated public catalog endpoint exists
 * yet for additional services — see apply-progress risk note); the section
 * degrades gracefully to "no hay servicios disponibles" without blocking the
 * step, since `servicios_apoyo` is optional in the submit payload.
 */

import { useEffect, useState } from 'react';

import apiClient from '@/lib/http/apiClient';

import { MATERIAL_EXTERNO_NOTICE, MONTAJE_REQUERIDO_OPTIONS } from '../constants';
import { useQuoteWizardStore } from '../store/quote-wizard.store';

interface AdditionalServiceOption {
  id: string;
  name: string;
}

export function StepServicios() {
  const serviciosApoyo = useQuoteWizardStore((s) => s.serviciosApoyo);
  const addServiceSelection = useQuoteWizardStore((s) => s.addServiceSelection);
  const removeServiceSelection = useQuoteWizardStore((s) => s.removeServiceSelection);
  const montajeRequerido = useQuoteWizardStore((s) => s.montajeRequerido);
  const requerimientosEspeciales = useQuoteWizardStore((s) => s.requerimientosEspeciales);
  const materialExterno = useQuoteWizardStore((s) => s.materialExterno);
  const materialExternoDetalle = useQuoteWizardStore((s) => s.materialExternoDetalle);
  const setField = useQuoteWizardStore((s) => s.setField);

  const [services, setServices] = useState<AdditionalServiceOption[]>([]);
  const [servicesUnavailable, setServicesUnavailable] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<AdditionalServiceOption[]>('/additional-services')
      .then((res) => {
        if (!cancelled) setServices(Array.isArray(res.data) ? res.data : []);
      })
      .catch(() => {
        if (!cancelled) setServicesUnavailable(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const isSelected = (serviceId: string) => serviciosApoyo.some((s) => s.serviceId === serviceId);

  const toggleService = (serviceId: string) => {
    if (isSelected(serviceId)) {
      removeServiceSelection(serviceId);
    } else {
      addServiceSelection({ serviceId, quantity: 1 });
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <h2 className="text-lg font-semibold text-gray-900">4. Servicios y montaje</h2>

      <div>
        <span className="block text-sm font-medium text-gray-700 mb-1">Servicios de apoyo (opcional)</span>
        {servicesUnavailable || services.length === 0 ? (
          <p className="text-xs text-gray-500">No hay servicios de apoyo disponibles en este momento.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {services.map((svc) => (
              <li key={svc.id}>
                <label className="inline-flex items-center gap-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={isSelected(svc.id)}
                    onChange={() => toggleService(svc.id)}
                  />
                  {svc.name}
                </label>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <label htmlFor="montaje_requerido" className="block text-sm font-medium text-gray-700 mb-1">
          Montaje requerido
        </label>
        <select
          id="montaje_requerido"
          value={montajeRequerido}
          onChange={(e) => setField('montajeRequerido', e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        >
          <option value="">Selecciona una opción</option>
          {MONTAJE_REQUERIDO_OPTIONS.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="requerimientos_especiales" className="block text-sm font-medium text-gray-700 mb-1">
          Requerimientos especiales (opcional)
        </label>
        <textarea
          id="requerimientos_especiales"
          rows={3}
          value={requerimientosEspeciales}
          onChange={(e) => setField('requerimientosEspeciales', e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
      </div>

      <fieldset>
        <legend className="block text-sm font-medium text-gray-700 mb-1">¿Ingresarás material externo?</legend>
        <div className="flex gap-4">
          <label className="inline-flex items-center gap-2 text-sm text-gray-700">
            <input
              type="radio"
              name="material_externo"
              checked={materialExterno === true}
              onChange={() => setField('materialExterno', true)}
            />
            Sí
          </label>
          <label className="inline-flex items-center gap-2 text-sm text-gray-700">
            <input
              type="radio"
              name="material_externo"
              checked={materialExterno === false}
              onChange={() => setField('materialExterno', false)}
            />
            No
          </label>
        </div>
      </fieldset>

      {materialExterno && (
        <div>
          <div className="rounded-lg border border-amber-100 bg-amber-50/60 px-4 py-3 text-sm text-amber-950 mb-2">
            {MATERIAL_EXTERNO_NOTICE}
          </div>
          <label htmlFor="material_externo_detalle" className="block text-sm font-medium text-gray-700 mb-1">
            Detalle del material externo
          </label>
          <textarea
            id="material_externo_detalle"
            rows={2}
            value={materialExternoDetalle}
            onChange={(e) => setField('materialExternoDetalle', e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
      )}
    </div>
  );
}
