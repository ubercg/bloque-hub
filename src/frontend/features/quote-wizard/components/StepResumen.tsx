'use client';

/**
 * Wizard Step 5 — Resumen, aceptaciones y envío (REQ-012 §4, RN-014).
 * Read-only summary of steps 1-4, both legal-acceptance checkboxes gating
 * submit, and the final multipart submit call.
 */

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

import apiClient from '@/lib/http/apiClient';

import { LEGAL_AVISO_PRIVACIDAD_URL, LEGAL_REGLAMENTO_URL } from '../constants';
import { useQuoteWizardStore } from '../store/quote-wizard.store';

interface SpaceOption {
  id: string;
  name: string;
}

const DOCUMENTS_BUCKET_KEY = 'adjuntos';

const FOLIO_NOT_ELIGIBLE_MESSAGE =
  'El folio ya no es elegible para continuar con la solicitud. Verifica el estatus en BLOQUE Portal.';
const PORTAL_UNAVAILABLE_MESSAGE =
  'El servicio de validación no está disponible en este momento. Intenta de nuevo más tarde.';
const SLOT_UNAVAILABLE_MESSAGE =
  'Uno de los espacios seleccionados ya no está disponible. Vuelve al paso 2 y ajusta tu selección.';
const DUPLICATE_FOLIO_MESSAGE = 'Ya existe una solicitud registrada con este folio.';
const VALIDATION_ERROR_MESSAGE = 'Revisa los datos capturados: algunos campos no son válidos.';
const GENERIC_ERROR_MESSAGE = 'Ocurrió un error al enviar tu solicitud. Intenta de nuevo.';

export function StepResumen() {
  const router = useRouter();
  const state = useQuoteWizardStore((s) => s);
  const setField = useQuoteWizardStore((s) => s.setField);

  const [spaces, setSpaces] = useState<SpaceOption[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const spaceName = (spaceId: string) => spaces.find((s) => s.id === spaceId)?.name ?? spaceId;
  const itemsTotal = state.items.reduce((acc, item) => acc + (item.cotizacionCalculada ?? 0), 0);
  const documentFiles = Array.isArray(state.documents[DOCUMENTS_BUCKET_KEY])
    ? (state.documents[DOCUMENTS_BUCKET_KEY] as File[])
    : [];

  const canSubmit = state.aceptaInfoCorrecta && state.aceptaReglamento && !isSubmitting;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setIsSubmitting(true);
    setError(null);

    const payload = {
      folio: state.folio,
      tipo_evento: state.tipoEvento,
      nombre_evento: state.nombreEvento || null,
      caracter_evento: state.caracterEvento,
      descripcion_evento: state.descripcionEvento || null,
      asistentes_estimados: state.asistentesEstimados,
      habra_prensa: state.habraPrensa,
      items: state.items.map((item) => ({
        space_id: item.spaceId,
        fecha: item.fecha,
        hora_inicio: item.horaInicio,
        hora_fin: item.horaFin,
      })),
      nombre_completo: state.nombreCompleto,
      cargo_puesto: state.cargoPuesto || null,
      institucion_organizacion: state.institucionOrganizacion || null,
      sector: state.sector,
      sector_otro: state.sectorOtro || null,
      correo_institucional: state.correoInstitucional,
      telefono_contacto: state.telefonoContacto,
      responsable_sitio_nombre: state.responsableSitioNombre || null,
      responsable_sitio_telefono: state.responsableSitioTelefono || null,
      como_conociste_bloque: state.comoConociste,
      como_conociste_otro: state.comoConocisteOtro || null,
      servicios_apoyo: state.serviciosApoyo.map((s) => ({
        service_id: s.serviceId,
        quantity: s.quantity,
      })),
      montaje_requerido: state.montajeRequerido,
      requerimientos_especiales: state.requerimientosEspeciales || null,
      material_externo: state.materialExterno,
      material_externo_detalle: state.materialExternoDetalle || null,
      acepta_info_correcta_autorizacion: state.aceptaInfoCorrecta,
      acepta_reglamento_y_aviso_privacidad: state.aceptaReglamento,
    };

    const fd = new FormData();
    fd.append('payload', JSON.stringify(payload));
    for (const file of documentFiles) {
      fd.append('files', file);
    }

    try {
      const res = await apiClient.post('/public/quote-requests', fd);
      const data = res.data as { quote_id: string; total: number; email_sent: boolean };
      const params = new URLSearchParams({
        total: String(data.total),
        email_sent: String(data.email_sent),
      });
      router.push(`/solicitud/confirmacion?${params.toString()}`);
      // Store reset happens on the confirmation screen (after it shows), not here.
    } catch (err: unknown) {
      const status =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { status?: number; data?: { detail?: { reason?: string } } } }).response
          : undefined;
      const reason = status?.data?.detail?.reason;

      if (status?.status === 403) {
        setError(FOLIO_NOT_ELIGIBLE_MESSAGE);
      } else if (status?.status === 503) {
        setError(PORTAL_UNAVAILABLE_MESSAGE);
      } else if (status?.status === 409 && reason === 'DUPLICATE_FOLIO') {
        setError(DUPLICATE_FOLIO_MESSAGE);
      } else if (status?.status === 409) {
        setError(SLOT_UNAVAILABLE_MESSAGE);
      } else if (status?.status === 422) {
        setError(VALIDATION_ERROR_MESSAGE);
      } else {
        setError(GENERIC_ERROR_MESSAGE);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <h2 className="text-lg font-semibold text-gray-900">5. Resumen y envío</h2>

      <section className="border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-900 mb-2">Evento</h3>
        <dl className="text-sm text-gray-700 space-y-1">
          <div>
            <dt className="inline font-medium">Tipo: </dt>
            <dd className="inline">{state.tipoEvento || '—'}</dd>
          </div>
          <div>
            <dt className="inline font-medium">Carácter: </dt>
            <dd className="inline">{state.caracterEvento || '—'}</dd>
          </div>
          <div>
            <dt className="inline font-medium">Asistentes estimados: </dt>
            <dd className="inline">{state.asistentesEstimados || '—'}</dd>
          </div>
          <div>
            <dt className="inline font-medium">¿Habrá prensa?: </dt>
            <dd className="inline">{state.habraPrensa ? 'Sí' : 'No'}</dd>
          </div>
        </dl>
      </section>

      <section className="border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-900 mb-2">Espacios</h3>
        <ul className="text-sm text-gray-700 space-y-1">
          {state.items.map((item, idx) => (
            <li key={`${item.spaceId}-${idx}`}>
              {spaceName(item.spaceId)} — {item.fecha} {item.horaInicio}-{item.horaFin}
              {typeof item.cotizacionCalculada === 'number' && (
                <span className="text-gray-500"> · ${item.cotizacionCalculada.toFixed(2)}</span>
              )}
            </li>
          ))}
        </ul>
        <p className="text-sm font-medium text-gray-900 mt-2">Total preliminar: ${itemsTotal.toFixed(2)}</p>
      </section>

      <section className="border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-900 mb-2">Solicitante</h3>
        <dl className="text-sm text-gray-700 space-y-1">
          <div>
            <dt className="inline font-medium">Nombre: </dt>
            <dd className="inline">{state.nombreCompleto || '—'}</dd>
          </div>
          <div>
            <dt className="inline font-medium">Correo: </dt>
            <dd className="inline">{state.correoInstitucional || '—'}</dd>
          </div>
          <div>
            <dt className="inline font-medium">Teléfono: </dt>
            <dd className="inline">{state.telefonoContacto || '—'}</dd>
          </div>
          <div>
            <dt className="inline font-medium">Sector: </dt>
            <dd className="inline">{state.sector === 'Otro' ? state.sectorOtro : state.sector || '—'}</dd>
          </div>
        </dl>
      </section>

      <section className="border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-900 mb-2">Servicios y montaje</h3>
        <dl className="text-sm text-gray-700 space-y-1">
          <div>
            <dt className="inline font-medium">Servicios de apoyo: </dt>
            <dd className="inline">{state.serviciosApoyo.length > 0 ? state.serviciosApoyo.length : 'Ninguno'}</dd>
          </div>
          <div>
            <dt className="inline font-medium">Montaje: </dt>
            <dd className="inline">{state.montajeRequerido || '—'}</dd>
          </div>
          <div>
            <dt className="inline font-medium">Material externo: </dt>
            <dd className="inline">{state.materialExterno ? 'Sí' : 'No'}</dd>
          </div>
        </dl>
      </section>

      <section className="border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-900 mb-2">Documentos</h3>
        {documentFiles.length > 0 ? (
          <ul className="text-sm text-gray-700 space-y-1">
            {documentFiles.map((f, i) => (
              <li key={`${f.name}-${i}`}>{f.name}</li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-gray-500">No adjuntaste documentos.</p>
        )}
      </section>

      <section className="flex flex-col gap-3">
        <label className="inline-flex items-start gap-2 text-sm text-gray-700">
          <input
            type="checkbox"
            checked={state.aceptaInfoCorrecta}
            onChange={(e) => setField('aceptaInfoCorrecta', e.target.checked)}
            className="mt-0.5"
          />
          Confirmo que la información proporcionada es correcta y estoy autorizado(a) para realizar esta solicitud.
        </label>
        <label className="inline-flex items-start gap-2 text-sm text-gray-700">
          <input
            type="checkbox"
            checked={state.aceptaReglamento}
            onChange={(e) => setField('aceptaReglamento', e.target.checked)}
            className="mt-0.5"
          />
          <span>
            He leído y acepto el{' '}
            <a href={LEGAL_REGLAMENTO_URL} target="_blank" rel="noopener noreferrer" className="text-blue-600 underline">
              Reglamento
            </a>{' '}
            y el{' '}
            <a
              href={LEGAL_AVISO_PRIVACIDAD_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 underline"
            >
              Aviso de Privacidad
            </a>
            .
          </span>
        </label>
      </section>

      {error && (
        <p role="alert" className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      <button
        type="button"
        disabled={!canSubmit}
        onClick={handleSubmit}
        className="w-full px-4 py-3 rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {isSubmitting ? 'Enviando solicitud...' : 'Enviar solicitud'}
      </button>
    </div>
  );
}
