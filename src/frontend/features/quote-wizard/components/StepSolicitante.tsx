'use client';

/**
 * Wizard Step 3 — Solicitante y documentos (REQ-012 §4.3/§4.4). Client
 * guards mirror RN-009/RN-010; the server is authoritative and re-validates
 * on submit.
 */

import { COMO_CONOCISTE_OPTIONS, COMO_CONOCISTE_OTRO, OFICIO_GOBIERNO_NOTE, SECTOR_OPTIONS, SECTOR_OTRO } from '../constants';
import { useQuoteWizardStore } from '../store/quote-wizard.store';
import { DocumentUpload } from './DocumentUpload';

export function StepSolicitante() {
  const nombreCompleto = useQuoteWizardStore((s) => s.nombreCompleto);
  const cargoPuesto = useQuoteWizardStore((s) => s.cargoPuesto);
  const institucionOrganizacion = useQuoteWizardStore((s) => s.institucionOrganizacion);
  const sector = useQuoteWizardStore((s) => s.sector);
  const sectorOtro = useQuoteWizardStore((s) => s.sectorOtro);
  const correoInstitucional = useQuoteWizardStore((s) => s.correoInstitucional);
  const telefonoContacto = useQuoteWizardStore((s) => s.telefonoContacto);
  const responsableSitioNombre = useQuoteWizardStore((s) => s.responsableSitioNombre);
  const responsableSitioTelefono = useQuoteWizardStore((s) => s.responsableSitioTelefono);
  const comoConociste = useQuoteWizardStore((s) => s.comoConociste);
  const comoConocisteOtro = useQuoteWizardStore((s) => s.comoConocisteOtro);
  const setField = useQuoteWizardStore((s) => s.setField);

  return (
    <div className="flex flex-col gap-5">
      <h2 className="text-lg font-semibold text-gray-900">3. Solicitante y documentos</h2>

      <div className="rounded-lg border border-blue-100 bg-blue-50/60 px-4 py-3 text-sm text-blue-950">
        {OFICIO_GOBIERNO_NOTE}
      </div>

      <div>
        <label htmlFor="nombre_completo" className="block text-sm font-medium text-gray-700 mb-1">
          Nombre completo
        </label>
        <input
          id="nombre_completo"
          type="text"
          value={nombreCompleto}
          onChange={(e) => setField('nombreCompleto', e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label htmlFor="cargo_puesto" className="block text-sm font-medium text-gray-700 mb-1">
            Cargo / puesto
          </label>
          <input
            id="cargo_puesto"
            type="text"
            value={cargoPuesto}
            onChange={(e) => setField('cargoPuesto', e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
        <div>
          <label htmlFor="institucion_organizacion" className="block text-sm font-medium text-gray-700 mb-1">
            Institución / organización
          </label>
          <input
            id="institucion_organizacion"
            type="text"
            value={institucionOrganizacion}
            onChange={(e) => setField('institucionOrganizacion', e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
      </div>

      <div>
        <label htmlFor="sector" className="block text-sm font-medium text-gray-700 mb-1">
          Sector
        </label>
        <select
          id="sector"
          value={sector}
          onChange={(e) => setField('sector', e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        >
          <option value="">Selecciona una opción</option>
          {SECTOR_OPTIONS.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      </div>

      {sector === SECTOR_OTRO && (
        <div>
          <label htmlFor="sector_otro" className="block text-sm font-medium text-gray-700 mb-1">
            Especifica el sector
          </label>
          <input
            id="sector_otro"
            type="text"
            value={sectorOtro}
            onChange={(e) => setField('sectorOtro', e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label htmlFor="correo_institucional" className="block text-sm font-medium text-gray-700 mb-1">
            Correo institucional
          </label>
          <input
            id="correo_institucional"
            type="email"
            value={correoInstitucional}
            onChange={(e) => setField('correoInstitucional', e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
        <div>
          <label htmlFor="telefono_contacto" className="block text-sm font-medium text-gray-700 mb-1">
            Teléfono de contacto
          </label>
          <input
            id="telefono_contacto"
            type="tel"
            value={telefonoContacto}
            onChange={(e) => setField('telefonoContacto', e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label htmlFor="responsable_sitio_nombre" className="block text-sm font-medium text-gray-700 mb-1">
            Responsable en sitio (opcional)
          </label>
          <input
            id="responsable_sitio_nombre"
            type="text"
            value={responsableSitioNombre}
            onChange={(e) => setField('responsableSitioNombre', e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
        <div>
          <label htmlFor="responsable_sitio_telefono" className="block text-sm font-medium text-gray-700 mb-1">
            Teléfono del responsable en sitio (opcional)
          </label>
          <input
            id="responsable_sitio_telefono"
            type="tel"
            value={responsableSitioTelefono}
            onChange={(e) => setField('responsableSitioTelefono', e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
      </div>

      <div>
        <label htmlFor="como_conociste" className="block text-sm font-medium text-gray-700 mb-1">
          ¿Cómo conociste BLOQUE?
        </label>
        <select
          id="como_conociste"
          value={comoConociste}
          onChange={(e) => setField('comoConociste', e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        >
          <option value="">Selecciona una opción</option>
          {COMO_CONOCISTE_OPTIONS.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      </div>

      {comoConociste === COMO_CONOCISTE_OTRO && (
        <div>
          <label htmlFor="como_conociste_otro" className="block text-sm font-medium text-gray-700 mb-1">
            Especifica cómo nos conociste
          </label>
          <input
            id="como_conociste_otro"
            type="text"
            value={comoConocisteOtro}
            onChange={(e) => setField('comoConocisteOtro', e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
      )}

      <DocumentUpload />
    </div>
  );
}
