'use client';

/**
 * Wizard Step 1 — Evento (REQ-012 §4.2). Client guards mirror RN-006/007/008;
 * the server is authoritative and re-validates on submit.
 */

import { CARACTER_EVENTO_OPTIONS, DESCRIPCION_EVENTO_MAX_WORDS, TIPO_EVENTO_OPTIONS, TIPO_EVENTO_OTRO } from '../constants';
import { useQuoteWizardStore } from '../store/quote-wizard.store';
import { countWords } from '../validation';

export function StepEvento() {
  const tipoEvento = useQuoteWizardStore((s) => s.tipoEvento);
  const nombreEvento = useQuoteWizardStore((s) => s.nombreEvento);
  const caracterEvento = useQuoteWizardStore((s) => s.caracterEvento);
  const descripcionEvento = useQuoteWizardStore((s) => s.descripcionEvento);
  const asistentesEstimados = useQuoteWizardStore((s) => s.asistentesEstimados);
  const habraPrensa = useQuoteWizardStore((s) => s.habraPrensa);
  const setField = useQuoteWizardStore((s) => s.setField);

  const wordCount = countWords(descripcionEvento);
  const overLimit = wordCount > DESCRIPCION_EVENTO_MAX_WORDS;

  return (
    <div className="flex flex-col gap-5">
      <h2 className="text-lg font-semibold text-gray-900">1. Datos del evento</h2>

      <div>
        <label htmlFor="tipo_evento" className="block text-sm font-medium text-gray-700 mb-1">
          Tipo de evento
        </label>
        <select
          id="tipo_evento"
          value={tipoEvento}
          onChange={(e) => setField('tipoEvento', e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        >
          <option value="">Selecciona una opción</option>
          {TIPO_EVENTO_OPTIONS.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      </div>

      {tipoEvento === TIPO_EVENTO_OTRO && (
        <div>
          <label htmlFor="nombre_evento" className="block text-sm font-medium text-gray-700 mb-1">
            Nombre del evento
          </label>
          <input
            id="nombre_evento"
            type="text"
            value={nombreEvento}
            onChange={(e) => setField('nombreEvento', e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
      )}

      <div>
        <label htmlFor="caracter_evento" className="block text-sm font-medium text-gray-700 mb-1">
          Carácter del evento
        </label>
        <select
          id="caracter_evento"
          value={caracterEvento}
          onChange={(e) => setField('caracterEvento', e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        >
          <option value="">Selecciona una opción</option>
          {CARACTER_EVENTO_OPTIONS.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="descripcion_evento" className="block text-sm font-medium text-gray-700 mb-1">
          Descripción del evento
        </label>
        <p className="text-xs text-gray-500 mb-1">
          Describe brevemente el objetivo y las actividades del evento (máximo {DESCRIPCION_EVENTO_MAX_WORDS} palabras).
        </p>
        <textarea
          id="descripcion_evento"
          rows={5}
          value={descripcionEvento}
          onChange={(e) => setField('descripcionEvento', e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
        <p className={`text-xs mt-1 ${overLimit ? 'text-red-600' : 'text-gray-500'}`}>
          {wordCount} / {DESCRIPCION_EVENTO_MAX_WORDS} palabras
          {overLimit ? ' — excede el límite permitido' : ''}
        </p>
      </div>

      <div>
        <label htmlFor="asistentes_estimados" className="block text-sm font-medium text-gray-700 mb-1">
          Asistentes estimados
        </label>
        <input
          id="asistentes_estimados"
          type="number"
          min={1}
          value={asistentesEstimados === 0 ? '' : asistentesEstimados}
          onChange={(e) => setField('asistentesEstimados', Number(e.target.value))}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
      </div>

      <fieldset>
        <legend className="block text-sm font-medium text-gray-700 mb-1">¿Habrá prensa?</legend>
        <div className="flex gap-4">
          <label className="inline-flex items-center gap-2 text-sm text-gray-700">
            <input
              type="radio"
              name="habra_prensa"
              checked={habraPrensa === true}
              onChange={() => setField('habraPrensa', true)}
            />
            Sí
          </label>
          <label className="inline-flex items-center gap-2 text-sm text-gray-700">
            <input
              type="radio"
              name="habra_prensa"
              checked={habraPrensa === false}
              onChange={() => setField('habraPrensa', false)}
            />
            No
          </label>
        </div>
      </fieldset>
    </div>
  );
}
