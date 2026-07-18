'use client';

/**
 * Wizard Step 2 — Espacio / fecha / cotización (REQ-012 §4, RN-012, design §6.6).
 * Multi-item: add/remove space+date/time blocks, check availability + price
 * per item via the public preview endpoints. Advisory only — submit always
 * recomputes the authoritative price server-side.
 */

import { useEffect, useState } from 'react';

import apiClient from '@/lib/http/apiClient';

import { useQuoteWizardStore } from '../store/quote-wizard.store';
import type { WizardItem } from '../store/quote-wizard.store';

interface SpaceOption {
  id: string;
  name: string;
}

interface DraftItem {
  spaceId: string;
  fecha: string;
  horaInicio: string;
  horaFin: string;
  status: 'idle' | 'checking' | 'ok' | 'unavailable' | 'no_pricing' | 'error';
  errorMessage: string | null;
  cotizacionCalculada?: number;
}

const EMPTY_DRAFT: DraftItem = {
  spaceId: '',
  fecha: '',
  horaInicio: '',
  horaFin: '',
  status: 'idle',
  errorMessage: null,
};

const UNAVAILABLE_MESSAGE = 'El espacio no está disponible en la fecha/horario seleccionados.';
const NO_PRICING_MESSAGE = 'No hay una regla de precio configurada para este espacio en esa fecha.';
const GENERIC_ERROR_MESSAGE = 'No se pudo calcular la disponibilidad/cotización. Intenta de nuevo.';

export function StepEspacio() {
  const items = useQuoteWizardStore((s) => s.items);
  const addItem = useQuoteWizardStore((s) => s.addItem);
  const removeItem = useQuoteWizardStore((s) => s.removeItem);

  const [spaces, setSpaces] = useState<SpaceOption[]>([]);
  const [draft, setDraft] = useState<DraftItem>(EMPTY_DRAFT);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<SpaceOption[]>('/spaces')
      .then((res) => {
        if (!cancelled) setSpaces(res.data);
      })
      .catch(() => {
        if (!cancelled) setSpaces([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const draftReady =
    draft.spaceId !== '' && draft.fecha !== '' && draft.horaInicio !== '' && draft.horaFin !== '';

  const handleCheckAndPrice = async () => {
    if (!draftReady) return;
    setDraft((d) => ({ ...d, status: 'checking', errorMessage: null }));

    try {
      const availabilityRes = await apiClient.post('/spaces/check-availability', {
        espacio_id: draft.spaceId,
        fecha: draft.fecha,
        hora_inicio: draft.horaInicio,
        hora_fin: draft.horaFin,
      });

      if (!availabilityRes.data.available) {
        setDraft((d) => ({ ...d, status: 'unavailable', errorMessage: UNAVAILABLE_MESSAGE }));
        return;
      }

      const priceRes = await apiClient.post('/public/quote-requests/price-preview', {
        items: [
          {
            space_id: draft.spaceId,
            fecha: draft.fecha,
            hora_inicio: draft.horaInicio,
            hora_fin: draft.horaFin,
          },
        ],
      });

      const price = priceRes.data.items[0]?.price as number | undefined;
      setDraft((d) => ({ ...d, status: 'ok', errorMessage: null, cotizacionCalculada: price }));
    } catch (err: unknown) {
      const status =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { status?: number } }).response?.status
          : undefined;
      if (status === 422) {
        setDraft((d) => ({ ...d, status: 'no_pricing', errorMessage: NO_PRICING_MESSAGE }));
      } else {
        setDraft((d) => ({ ...d, status: 'error', errorMessage: GENERIC_ERROR_MESSAGE }));
      }
    }
  };

  const handleAddItem = () => {
    if (draft.status !== 'ok' || typeof draft.cotizacionCalculada !== 'number') return;
    const item: WizardItem = {
      spaceId: draft.spaceId,
      fecha: draft.fecha,
      horaInicio: draft.horaInicio,
      horaFin: draft.horaFin,
      cotizacionCalculada: draft.cotizacionCalculada,
    };
    addItem(item);
    setDraft(EMPTY_DRAFT);
  };

  const spaceName = (spaceId: string) => spaces.find((s) => s.id === spaceId)?.name ?? spaceId;
  const total = items.reduce((acc, item) => acc + (item.cotizacionCalculada ?? 0), 0);

  return (
    <div className="flex flex-col gap-5">
      <h2 className="text-lg font-semibold text-gray-900">2. Espacio, fecha y cotización</h2>
      <p className="text-xs text-gray-500">
        Agrega uno o más espacios con su fecha y horario. La cotización mostrada es preliminar; el
        precio final se confirma al enviar tu solicitud.
      </p>

      {items.length > 0 && (
        <ul className="flex flex-col gap-2">
          {items.map((item, index) => (
            <li
              key={`${item.spaceId}-${item.fecha}-${item.horaInicio}-${index}`}
              className="flex items-center justify-between border border-gray-200 rounded-lg px-3 py-2"
            >
              <div className="text-sm text-gray-700">
                <span className="font-medium">{spaceName(item.spaceId)}</span> — {item.fecha}{' '}
                {item.horaInicio}-{item.horaFin}
                {typeof item.cotizacionCalculada === 'number' && (
                  <span className="text-gray-500"> · ${item.cotizacionCalculada.toFixed(2)}</span>
                )}
              </div>
              <button
                type="button"
                onClick={() => removeItem(index)}
                className="text-sm text-red-600 hover:text-red-700"
              >
                Quitar
              </button>
            </li>
          ))}
        </ul>
      )}

      {items.length > 0 && (
        <p className="text-sm font-medium text-gray-900">Total preliminar: ${total.toFixed(2)}</p>
      )}

      <div className="border border-dashed border-gray-300 rounded-lg p-4 flex flex-col gap-3">
        <div>
          <label htmlFor="space_id" className="block text-sm font-medium text-gray-700 mb-1">
            Espacio
          </label>
          <select
            id="space_id"
            value={draft.spaceId}
            onChange={(e) => setDraft({ ...EMPTY_DRAFT, spaceId: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          >
            <option value="">Selecciona un espacio</option>
            {spaces.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <label htmlFor="fecha" className="block text-sm font-medium text-gray-700 mb-1">
              Fecha
            </label>
            <input
              id="fecha"
              type="date"
              value={draft.fecha}
              onChange={(e) => setDraft((d) => ({ ...d, fecha: e.target.value, status: 'idle', errorMessage: null }))}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <div>
            <label htmlFor="hora_inicio" className="block text-sm font-medium text-gray-700 mb-1">
              Hora inicio
            </label>
            <input
              id="hora_inicio"
              type="time"
              value={draft.horaInicio}
              onChange={(e) =>
                setDraft((d) => ({ ...d, horaInicio: e.target.value, status: 'idle', errorMessage: null }))
              }
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <div>
            <label htmlFor="hora_fin" className="block text-sm font-medium text-gray-700 mb-1">
              Hora fin
            </label>
            <input
              id="hora_fin"
              type="time"
              value={draft.horaFin}
              onChange={(e) => setDraft((d) => ({ ...d, horaFin: e.target.value, status: 'idle', errorMessage: null }))}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
        </div>

        {draft.status === 'unavailable' || draft.status === 'no_pricing' || draft.status === 'error' ? (
          <p role="alert" className="text-sm text-red-600">
            {draft.errorMessage}
          </p>
        ) : null}

        {draft.status === 'ok' && typeof draft.cotizacionCalculada === 'number' && (
          <p className="text-sm text-green-700">
            Disponible — cotización preliminar: ${draft.cotizacionCalculada.toFixed(2)}
          </p>
        )}

        <div className="flex gap-3">
          <button
            type="button"
            disabled={!draftReady || draft.status === 'checking'}
            onClick={handleCheckAndPrice}
            className="px-4 py-2 rounded-lg border border-blue-600 text-blue-600 font-medium hover:bg-blue-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {draft.status === 'checking' ? 'Verificando...' : 'Verificar disponibilidad y precio'}
          </button>
          <button
            type="button"
            disabled={draft.status !== 'ok'}
            onClick={handleAddItem}
            className="px-4 py-2 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Agregar espacio
          </button>
        </div>
      </div>
    </div>
  );
}
