'use client';

/**
 * Booking Confirmation Page
 * Cotización tipo tabla + datos del evento + contacto
 */

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useEventCartStore } from '@/features/booking';
import {
  buildOrderTableRows,
  type PricingBySpaceId,
  formatFechasEventoSpanish,
  formatHorarioEvento,
  formatReservationPeriodBoundsEs,
  sumDistinctSpaceCapacities,
  todayIsoMexico,
  uniqueCartDatesSorted,
} from '@/features/booking/lib/confirm-summary';
import apiClient from '@/lib/http/apiClient';
import {
  Building2,
  Calendar,
  CheckCircle2,
  Clock,
  FileUp,
  Mail,
  Phone,
  User,
  Users,
  AlertCircle,
  PartyPopper,
  FileText,
} from 'lucide-react';
import useSWR from 'swr';

function formatCantidad(n: number): string {
  if (Number.isInteger(n)) return String(n);
  return n.toLocaleString('es-MX', { maximumFractionDigits: 2 });
}

const DEFAULT_EMPRESA = '';
const DEFAULT_NOMBRE_EVENTO =
  '';
const fetcher = (url: string) => apiClient.get(url).then((res) => res.data);

interface SpaceApi {
  id: string;
  precio_por_hora: number;
}

interface PricingRuleApi {
  space_id: string;
  base_6h: number;
  base_12h: number;
  extra_hour_rate: number;
  effective_from?: string;
}

interface DiscountValidateResponse {
  valid: boolean;
  code: string;
  discount_code_id?: string;
  discount_type?: 'PERCENT' | 'FIXED';
  discount_value?: string | number;
  discount_amount: string | number;
  subtotal: string | number;
  total: string | number;
  reason?: string | null;
}

interface DocumentTypeDefinitionApi {
  id: string;
  code: string;
  label: string;
  required: boolean;
  requires_condition: string;
  mime_rules: string[];
  active: boolean;
  sort_order: number;
}

interface CompletenessApi {
  required: Array<{
    type: string;
    label: string;
    status: 'OK' | 'MISSING' | 'REQUIRES_UPDATE';
    document_id?: string | null;
  }>;
  optional: Array<{
    type: string;
    label: string;
    status: 'OK' | 'MISSING' | 'REQUIRES_UPDATE';
    document_id?: string | null;
  }>;
  is_complete: boolean;
}

interface PostBookingContext {
  group_event_id: string;
  first_reservation_id: string;
  grandTotal: number;
  count: number;
  ttl?: string;
}

function extractAxiosDetail(err: unknown): string | undefined {
  if (!err || typeof err !== 'object' || !('response' in err)) return undefined;
  const data = (err as { response?: { data?: { detail?: unknown } } }).response?.data;
  const detail = data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string };
    if (typeof first?.msg === 'string') return first.msg;
  }
  return undefined;
}

/** Mensajes en español para códigos que devuelve el backend en `detail`. */
function mapBookingErrorDetail(detail: string | undefined, fallback: string): string {
  if (!detail) return fallback;
  const map: Record<string, string> = {
    DOCUMENTATION_INCOMPLETE:
      'Faltan documentos obligatorios o no pasaron la validación. Revisa los archivos e intenta de nuevo.',
    SLOT_NO_DISPONIBLE:
      'Este horario ya no está disponible. Elige otro slot o vuelve al catálogo.',
    INVALID_MIME: 'Uno de los archivos no tiene un formato permitido (PDF, JPG o PNG).',
    FILE_TOO_LARGE: 'Uno de los archivos supera el tamaño máximo permitido.',
    FILE_EMPTY: 'Uno de los archivos está vacío.',
    GROUP_QUOTA_EXCEEDED: 'Se alcanzó el límite de archivos para esta solicitud.',
    UNKNOWN_DOCUMENT_TYPE: 'Tipo de documento no reconocido. Recarga la página e intenta de nuevo.',
    GROUP_NOT_FOUND: 'No se encontró el grupo de reserva. Vuelve a intentar desde el inicio.',
    FORBIDDEN: 'No tienes permiso para subir este documento.',
    INVALID_STATE: 'El estado de la reserva no permite subir documentos en este momento.',
    DISCOUNT_DOC_NOT_APPLICABLE: 'Este documento no aplica a tu solicitud.',
    DISCOUNT_CODE_INVALID: 'El código de descuento no existe.',
    DISCOUNT_CODE_INACTIVE: 'El código de descuento está inactivo.',
    DISCOUNT_CODE_EXPIRED: 'El código de descuento está expirado.',
    DISCOUNT_CODE_USAGE_LIMIT_REACHED: 'El código alcanzó su límite de usos.',
    DISCOUNT_CODE_MIN_SUBTOTAL_NOT_MET: 'El subtotal no cumple el mínimo para usar este código.',
    DISCOUNT_CODE_ALREADY_USED_BY_USER: 'Ya usaste este código anteriormente.',
  };
  return map[detail] ?? detail;
}

export default function ConfirmBookingPage() {
  const router = useRouter();
  const { items, clearCart } = useEventCartStore();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [discountCodeInput, setDiscountCodeInput] = useState('');
  const [appliedDiscountCode, setAppliedDiscountCode] = useState<string | null>(null);
  const [discountAmount, setDiscountAmount] = useState(0);
  const [discountMessage, setDiscountMessage] = useState<string | null>(null);
  const [validatingDiscount, setValidatingDiscount] = useState(false);

  /** Tras POST exitoso: permite completar documentación si falló la subida o quedó incompleta. */
  const [postCtx, setPostCtx] = useState<PostBookingContext | null>(null);
  /** Archivos elegidos antes de crear la reserva (misma etapa que el formulario). */
  const [pendingFiles, setPendingFiles] = useState<Record<string, File | File[]>>({});
  const [docUploadError, setDocUploadError] = useState<string | null>(null);
  const [uploadingCode, setUploadingCode] = useState<string | null>(null);

  const { data: spaces = [] } = useSWR<SpaceApi[]>('/spaces', fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 60000,
  });
  const { data: pricingRules = [] } = useSWR<PricingRuleApi[]>('/pricing-rules', fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 60000,
  });

  const groupEventId = postCtx?.group_event_id;
  const loadDocumentDefinitions = items.length > 0 || postCtx !== null;
  const { data: docDefinitions = [], isLoading: docDefsLoading } = useSWR<DocumentTypeDefinitionApi[]>(
    loadDocumentDefinitions ? '/document-type-definitions' : null,
    fetcher,
    { revalidateOnFocus: false }
  );
  const {
    data: completeness,
    mutate: mutateCompleteness,
    isLoading: completenessLoading,
  } = useSWR<CompletenessApi>(
    groupEventId ? `/group-events/${groupEventId}/documents/completeness` : null,
    fetcher,
    { revalidateOnFocus: false }
  );

  const definitionByCode = useMemo(() => {
    const m = new Map<string, DocumentTypeDefinitionApi>();
    for (const d of docDefinitions) m.set(d.code, d);
    return m;
  }, [docDefinitions]);

  /** Lista para mostrar en paso 1 (misma lógica condicional que completeness en servidor). */
  const docPreviewLists = useMemo(() => {
    if (!docDefinitions.length) return { required: [] as DocumentTypeDefinitionApi[], optional: [] as DocumentTypeDefinitionApi[] };
    const hasDiscount = Boolean(appliedDiscountCode);
    const required: DocumentTypeDefinitionApi[] = [];
    const optional: DocumentTypeDefinitionApi[] = [];
    const sorted = [...docDefinitions].sort((a, b) => a.sort_order - b.sort_order);
    for (const d of sorted) {
      if (!d.active) continue;
      if (d.requires_condition === 'DISCOUNT_CODE' && !hasDiscount) continue;
      if (d.required) required.push(d);
      else optional.push(d);
    }
    return { required, optional };
  }, [docDefinitions, appliedDiscountCode]);

  const hasAllRequiredPendingFiles = useMemo(() => {
    for (const d of docPreviewLists.required) {
      const p = pendingFiles[d.code];
      if (!p || !(p instanceof File)) return false;
    }
    return true;
  }, [docPreviewLists.required, pendingFiles]);

  const pricingBySpaceId = useMemo<PricingBySpaceId>(() => {
    const byId: PricingBySpaceId = {};
    const rulesMap = new Map(pricingRules.map((r) => [r.space_id, r]));
    for (const s of spaces) {
      const rule = rulesMap.get(s.id);
      const porHora = rule?.extra_hour_rate ?? s.precio_por_hora ?? 0;
      byId[s.id] = {
        porHora,
        seisHoras: rule?.base_6h ?? 0,
        doceHoras: rule?.base_12h ?? 0,
        semana: 0,
        mes: 0,
      };
    }
    return byId;
  }, [spaces, pricingRules]);

  const orderRows = useMemo(() => buildOrderTableRows(items, pricingBySpaceId), [items, pricingBySpaceId]);
  const total = useMemo(
    () => orderRows.reduce((acc, row) => acc + row.total, 0),
    [orderRows]
  );
  const grandTotal = Math.max(0, total - discountAmount);
  const fechasEvento = useMemo(() => uniqueCartDatesSorted(items), [items]);
  const fechaEventoTexto = useMemo(() => formatFechasEventoSpanish(fechasEvento), [fechasEvento]);
  const horarioTexto = useMemo(() => formatHorarioEvento(items), [items]);
  const periodoReservacionTexto = useMemo(() => formatReservationPeriodBoundsEs(items), [items]);
  const capacidadSugerida = useMemo(() => sumDistinctSpaceCapacities(items), [items]);

  const [fechaSolicitud, setFechaSolicitud] = useState(todayIsoMexico);
  const [empresa, setEmpresa] = useState(DEFAULT_EMPRESA);
  const [nombreEvento, setNombreEvento] = useState(DEFAULT_NOMBRE_EVENTO);
  const [aforo, setAforo] = useState<number>(() => {
    const c = sumDistinctSpaceCapacities(items);
    return c > 0 ? c : 400;
  });

  const [formData, setFormData] = useState({
    nombre_contacto: '',
    email: '',
    telefono: '',
    tipo_cliente: 'B2B',
    notas: '',
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (postCtx) return;
    setIsSubmitting(true);
    setError(null);
    setDocUploadError(null);

    if (docDefsLoading || !docDefinitions.length) {
      setError('Espera a cargar los tipos de documento o recarga la página.');
      setIsSubmitting(false);
      return;
    }
    if (!hasAllRequiredPendingFiles) {
      setError('Adjunta todos los documentos obligatorios (PDF, JPG o PNG).');
      setIsSubmitting(false);
      return;
    }

    const bloqueEvento = [
      `Fecha de solicitud: ${fechaSolicitud}`,
      `Empresa: ${empresa}`,
      `Nombre del evento: ${nombreEvento}`,
      `Fecha(s) del evento: ${fechaEventoTexto}`,
      `Periodo de reservación (inicio → fin): ${periodoReservacionTexto}`,
      `Horario (rango horario global): ${horarioTexto}`,
      `Aforo declarado: ${aforo} personas`,
    ].join('\n');

    const notasCompletas = [bloqueEvento, formData.notas].filter(Boolean).join('\n\n---\n');

    try {
      const eventBody = {
        event_name: nombreEvento || null,
        discount_code: appliedDiscountCode,
        items: items.map((item) => ({
          space_id: item.spaceId,
          fecha: item.fecha,
          hora_inicio: item.horaInicio.length === 5 ? `${item.horaInicio}:00` : item.horaInicio,
          hora_fin: item.horaFin.length === 5 ? `${item.horaFin}:00` : item.horaFin,
        })),
      };

      const pairs: { id: string; file: File }[] = [];
      for (const d of [...docPreviewLists.required, ...docPreviewLists.optional]) {
        const entry = pendingFiles[d.code];
        if (!entry) continue;
        if (Array.isArray(entry)) {
          for (const f of entry) pairs.push({ id: d.id, file: f });
        } else if (entry instanceof File) {
          pairs.push({ id: d.id, file: entry });
        }
      }

      const fd = new FormData();
      fd.append('payload', JSON.stringify(eventBody));
      fd.append('document_type_ids', JSON.stringify(pairs.map((p) => p.id)));
      for (const p of pairs) {
        fd.append('files', p.file);
      }

      const response = await apiClient.post('/reservation-events/with-documents', fd);
      const payload = response.data as {
        group_event_id: string;
        reservations: Array<{ id: string; ttl_expires_at?: string }>;
      };
      const created = payload.reservations ?? [];
      if (created.length === 0) {
        throw new Error('No se crearon reservaciones para el evento');
      }

      const first = created[0];

      clearCart();

      try {
        sessionStorage.setItem(
          'bloque_booking_confirm_context',
          JSON.stringify({
            fechaSolicitud,
            empresa,
            nombreEvento,
            fechasEvento: fechaEventoTexto,
            periodoReservacion: periodoReservacionTexto,
            horario: horarioTexto,
            aforo,
            notas: notasCompletas,
            descuento: discountAmount,
            codigoDescuento: appliedDiscountCode,
          })
        );
      } catch {
        /* ignore */
      }

      const params = new URLSearchParams({
        id: first.id,
        total: String(grandTotal),
        count: String(created.length),
      });
      params.set('group_event_id', payload.group_event_id);
      if (first.ttl_expires_at) params.set('ttl', first.ttl_expires_at);
      router.push(`/booking/success?${params.toString()}`);
    } catch (err: unknown) {
      console.error('Error al crear reserva:', err);
      const status =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { status?: number } }).response?.status
          : undefined;
      const detail = extractAxiosDetail(err);
      const detailStr = typeof detail === 'string' ? detail : undefined;
      if (status === 409) {
        setError(
          detailStr?.includes('SLOT')
            ? 'Este horario acaba de ser reservado. Por favor elige otro slot o vuelve al catálogo.'
            : 'Uno de los espacios ya no está disponible. Revisa el catálogo y vuelve a intentar.'
        );
      } else if (status === 400) {
        setError(
          mapBookingErrorDetail(
            detailStr,
            'No se pudo registrar la solicitud. Revisa los archivos (formato y tamaño) e intenta de nuevo.'
          )
        );
      } else if (status === 422) {
        setError(
          detailStr
            ? `Datos no válidos: ${detailStr}`
            : 'Los datos enviados no son válidos. Recarga la página e intenta de nuevo.'
        );
      } else {
        setError(
          detailStr
            ? mapBookingErrorDetail(detailStr, detailStr)
            : 'Error al procesar la reserva. Por favor intenta nuevamente.'
        );
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const applyDiscountCode = async () => {
    const raw = discountCodeInput.trim();
    if (!raw) {
      setDiscountMessage('Ingresa un código de descuento.');
      return;
    }
    setValidatingDiscount(true);
    setDiscountMessage(null);
    try {
      const payload = {
        code: raw,
        subtotal: total,
      };
      const resp = await apiClient.post<DiscountValidateResponse>('/discount-codes/validate', payload);
      const data = resp.data;
      if (!data.valid) {
        const byReason: Record<string, string> = {
          DISCOUNT_CODE_INVALID: 'El código no existe.',
          DISCOUNT_CODE_INACTIVE: 'El código está inactivo.',
          DISCOUNT_CODE_EXPIRED: 'El código está expirado.',
          DISCOUNT_CODE_USAGE_LIMIT_REACHED: 'El código alcanzó su límite de usos.',
          DISCOUNT_CODE_MIN_SUBTOTAL_NOT_MET: 'El subtotal no cumple el mínimo para usar este código.',
          DISCOUNT_CODE_ALREADY_USED_BY_USER: 'Ya usaste este código anteriormente.',
        };
        setAppliedDiscountCode(null);
        setDiscountAmount(0);
        setDiscountMessage(byReason[data.reason ?? ''] ?? 'No se pudo aplicar el código.');
        return;
      }
      const amount = Number(data.discount_amount ?? 0);
      setAppliedDiscountCode(data.code);
      setDiscountAmount(Number.isFinite(amount) ? amount : 0);
      setDiscountMessage(`Código aplicado: ${data.code}`);
    } catch {
      setAppliedDiscountCode(null);
      setDiscountAmount(0);
      setDiscountMessage('No se pudo validar el código en este momento.');
    } finally {
      setValidatingDiscount(false);
    }
  };

  const clearDiscountCode = () => {
    setAppliedDiscountCode(null);
    setDiscountAmount(0);
    setDiscountMessage(null);
    setDiscountCodeInput('');
  };

  const goToSuccess = () => {
    if (!postCtx) return;
    const params = new URLSearchParams({
      id: postCtx.first_reservation_id,
      total: String(postCtx.grandTotal),
      count: String(postCtx.count),
    });
    params.set('group_event_id', postCtx.group_event_id);
    if (postCtx.ttl) params.set('ttl', postCtx.ttl);
    router.push(`/booking/success?${params.toString()}`);
  };

  const uploadForType = async (code: string, file: File) => {
    const def = definitionByCode.get(code);
    if (!postCtx || !def) return;
    setDocUploadError(null);
    setUploadingCode(code);
    try {
      const fd = new FormData();
      fd.append('document_type_id', def.id);
      fd.append('file', file);
      await apiClient.post(`/group-events/${postCtx.group_event_id}/documents`, fd);
      await mutateCompleteness();
    } catch (err: unknown) {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
          : undefined;
      setDocUploadError(
        typeof detail === 'string'
          ? mapBookingErrorDetail(detail, detail)
          : 'No se pudo subir el archivo. Intenta de nuevo.'
      );
    } finally {
      setUploadingCode(null);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
  };

  if (items.length === 0 && postCtx) {
    const docRows = [
      ...(completeness?.required ?? []),
      ...(completeness?.optional ?? []),
    ];

    return (
      <div className="max-w-3xl mx-auto p-4 sm:p-8">
        <div className="rounded-lg border border-amber-200 bg-amber-50/80 px-4 py-3 text-sm text-amber-950 mb-6">
          Tu solicitud ya está registrada. Completa la documentación para que comercial u operaciones puedan validar y
          generar el pase de caja. Formatos: PDF, JPG o PNG.
        </div>
        <h1 className="text-3xl font-bold mb-2">Completar documentación</h1>
        <p className="text-gray-600 mb-6">
          Sube o reemplaza archivos (arrastra o elige archivo). Los obligatorios deben quedar en estado listo antes de
          continuar.
        </p>

        {docUploadError && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-3 mb-6">
            <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-red-700">{docUploadError}</div>
          </div>
        )}

        <section className="bg-white rounded-xl shadow border border-gray-200 p-6 space-y-6">
          {(completenessLoading && !completeness) || docDefsLoading ? (
            <p className="text-gray-600">Cargando requisitos…</p>
          ) : (
            docRows.map((row) => {
              const inputId = `kyc-file-${row.type}`;
              const busy = uploadingCode === row.type;
              return (
                <div key={row.type} className="border border-gray-100 rounded-lg p-4">
                  <div className="flex items-start justify-between gap-4 mb-3">
                    <div>
                      <p className="font-semibold text-gray-900">{row.label}</p>
                      <p className="text-xs text-gray-500">{row.type}</p>
                    </div>
                    {row.status === 'OK' ? (
                      <span className="inline-flex items-center gap-1 text-sm text-emerald-700">
                        <CheckCircle2 className="w-4 h-4" /> Listo
                      </span>
                    ) : (
                      <span className="text-sm text-amber-700">Pendiente</span>
                    )}
                  </div>
                  <label
                    htmlFor={inputId}
                    onDragOver={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                    }}
                    onDrop={(e) => {
                      e.preventDefault();
                      const f = e.dataTransfer.files[0];
                      if (f) void uploadForType(row.type, f);
                    }}
                    className="flex flex-col items-center justify-center gap-2 border-2 border-dashed border-gray-200 rounded-lg px-4 py-8 cursor-pointer hover:border-blue-400 hover:bg-blue-50/40 transition"
                  >
                    <FileUp className="w-8 h-8 text-gray-400" />
                    <span className="text-sm text-gray-700">
                      {busy ? 'Subiendo…' : 'Arrastra aquí o haz clic para elegir archivo'}
                    </span>
                    <input
                      id={inputId}
                      type="file"
                      accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                      className="hidden"
                      disabled={busy}
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) void uploadForType(row.type, f);
                        e.target.value = '';
                      }}
                    />
                  </label>
                </div>
              );
            })
          )}
        </section>

        <div className="mt-8 flex justify-end">
          <button
            type="button"
            disabled={!completeness?.is_complete}
            onClick={goToSuccess}
            className="px-6 py-3 rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
          >
            Continuar
          </button>
        </div>
        {!completeness?.is_complete && completeness && (
          <p className="text-xs text-gray-500 mt-3 text-center sm:text-right">
            Completa todos los documentos obligatorios para continuar.
          </p>
        )}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="max-w-2xl mx-auto p-8 text-center">
        <AlertCircle className="w-16 h-16 text-yellow-500 mx-auto mb-4" />
        <h2 className="text-2xl font-bold mb-2">Carrito vacío</h2>
        <p className="text-gray-600 mb-6">
          No tienes espacios en tu carrito. Agrega espacios desde el catálogo.
        </p>
        <button
          onClick={() => router.push('/catalog')}
          className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-semibold"
        >
          Ir al Catálogo
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto p-4 sm:p-8">
      <h1 className="text-3xl font-bold mb-2">Confirmar Reserva</h1>
      <p className="text-sm text-gray-600 mb-2">
        <span className="font-semibold text-blue-800">Solicitud y documentación</span>
        <span className="text-gray-500">
          {' '}
          — En un solo envío: datos del evento y archivos para expediente (comercial/operaciones validan antes del pase
          de caja).
        </span>
      </p>
      <p className="text-gray-600 mb-8">Revisa los detalles de tu reserva y completa la información</p>

      <form onSubmit={handleSubmit} className="space-y-10">
        {/* Detalle de cotización */}
        <section className="bg-white rounded-xl shadow border border-gray-200 overflow-hidden">
          <div className="px-4 sm:px-6 py-4 border-b border-gray-100 bg-gray-50/80">
            <h2 className="text-lg font-bold text-gray-900">Detalle de Espacios</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[640px]">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50 text-left text-gray-700">
                  <th className="px-4 py-3 font-semibold">Espacio</th>
                  <th className="px-4 py-3 font-semibold whitespace-nowrap">Tiempo</th>
                  <th className="px-4 py-3 font-semibold text-right whitespace-nowrap">Precio unitario</th>
                  <th className="px-4 py-3 font-semibold text-right whitespace-nowrap">Cantidad</th>
                  <th className="px-4 py-3 font-semibold text-right whitespace-nowrap">Total</th>
                </tr>
              </thead>
              <tbody>
                {orderRows.map((row) => (
                  <tr key={row.key} className="border-b border-gray-100 hover:bg-gray-50/50">
                    <td className="px-4 py-3 text-gray-900 align-top">{row.espacio}</td>
                    <td className="px-4 py-3 text-gray-700 whitespace-nowrap align-top">{row.tiempoLabel}</td>
                    <td className="px-4 py-3 text-right text-gray-800 align-top">
                      ${row.precioUnitario.toLocaleString('es-MX')}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-800 align-top">{formatCantidad(row.cantidad)}</td>
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
              <label className="block text-sm font-medium text-gray-700 mb-2">Código de descuento</label>
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
                <p className={`mt-2 text-xs ${appliedDiscountCode ? 'text-emerald-700' : 'text-red-700'}`}>
                  {discountMessage}
                </p>
              )}
            </div>
            <div className="flex justify-between gap-4">
              <span className="font-medium text-gray-700">Subtotal:</span>
              <span className="font-semibold text-gray-900">${total.toLocaleString('es-MX')}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="font-medium text-gray-700">Descuento:</span>
              <span className="text-gray-800">
                {discountAmount > 0 ? `-$${discountAmount.toLocaleString('es-MX')}` : '—'}
              </span>
            </div>
            <div className="flex justify-between gap-4 text-base pt-1 border-t border-gray-200">
              <span className="font-bold text-gray-900">Total:</span>
              <span className="font-bold text-blue-600 text-lg">${grandTotal.toLocaleString('es-MX')}</span>
            </div>
          </div>
        </section>

        {/* Datos del evento / solicitud */}
        <section className="bg-white rounded-xl shadow border border-gray-200 p-6">
          <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
            <PartyPopper className="w-5 h-5 text-purple-600" />
            Datos del evento
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                <Calendar className="w-4 h-4 inline mr-1" />
                Fecha (solicitud)
              </label>
              <input
                type="date"
                value={fechaSolicitud}
                onChange={(e) => setFechaSolicitud(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <p className="text-xs text-gray-500 mt-1">Por defecto: hoy (zona México). Puedes ajustarla.</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                <Building2 className="w-4 h-4 inline mr-1" />
                Empresa
              </label>
              <input
                type="text"
                value={empresa}
                onChange={(e) => setEmpresa(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Razón social o nombre de la organización"
              />
            </div>

            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-2">Nombre del evento</label>
              <input
                type="text"
                value={nombreEvento}
                onChange={(e) => setNombreEvento(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                <Calendar className="w-4 h-4 inline mr-1" />
                Periodo de reservación (inicio → fin)
              </label>
              <div className="w-full px-4 py-3 border border-dashed border-gray-200 rounded-lg bg-gray-50 text-gray-800 text-sm min-h-[42px] flex items-center">
                {periodoReservacionTexto}
              </div>
              <p className="text-xs text-gray-500 mt-1">
                Desde el primer inicio hasta el último fin de todos los espacios (reservación continua).
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                <Calendar className="w-4 h-4 inline mr-1" />
                Fecha del evento
              </label>
              <div className="w-full px-4 py-2 border border-dashed border-gray-200 rounded-lg bg-gray-50 text-gray-800 text-sm min-h-[42px] flex items-center">
                {fechaEventoTexto}
              </div>
              <p className="text-xs text-gray-500 mt-1">Días calendario cubiertos en el periodo.</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                <Clock className="w-4 h-4 inline mr-1" />
                Horario
              </label>
              <div className="w-full px-4 py-2 border border-dashed border-gray-200 rounded-lg bg-gray-50 text-gray-800 text-sm min-h-[42px] flex items-center">
                {horarioTexto}
              </div>
              <p className="text-xs text-gray-500 mt-1">
                Entre la hora de inicio más temprana y la de fin más tardía (p. ej. 8:00 a. m. a 8:00 p. m.).
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                <Users className="w-4 h-4 inline mr-1" />
                Aforo (personas)
              </label>
              <input
                type="number"
                min={1}
                value={aforo}
                onChange={(e) => setAforo(parseInt(e.target.value, 10) || 0)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <p className="text-xs text-gray-500 mt-1">
                Sugerido: suma de capacidades de los espacios en carrito ({capacidadSugerida || '—'}).
              </p>
            </div>
          </div>
        </section>

        {/* Contacto */}
        <section className="bg-white rounded-xl shadow border border-gray-200 p-6">
          <h2 className="text-xl font-bold mb-4">Información de contacto</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                <User className="w-4 h-4 inline mr-1" />
                Nombre de contacto *
              </label>
              <input
                type="text"
                name="nombre_contacto"
                required
                value={formData.nombre_contacto}
                onChange={handleChange}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Ej: Juan Pérez"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                <Mail className="w-4 h-4 inline mr-1" />
                Correo electrónico *
              </label>
              <input
                type="email"
                name="email"
                required
                value={formData.email}
                onChange={handleChange}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="correo@ejemplo.com"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                <Phone className="w-4 h-4 inline mr-1" />
                Teléfono *
              </label>
              <input
                type="tel"
                name="telefono"
                required
                value={formData.telefono}
                onChange={handleChange}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="5512345678"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Tipo de cliente</label>
              <select
                name="tipo_cliente"
                value={formData.tipo_cliente}
                onChange={handleChange}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="B2B">Empresa (B2B)</option>
                <option value="B2C">Individual (B2C)</option>
                <option value="GOBIERNO">Gobierno</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Notas adicionales (opcional)</label>
              <textarea
                name="notas"
                value={formData.notas}
                onChange={handleChange}
                rows={3}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Requerimientos especiales, instrucciones, etc."
              />
            </div>
          </div>
        </section>

        {/* Documentación del expediente (misma etapa; se envía al servidor tras crear la reserva) */}
        <section className="bg-white rounded-xl shadow border border-gray-200 p-6">
          <h2 className="text-xl font-bold mb-2 flex items-center gap-2">
            <FileText className="w-5 h-5 text-slate-700" />
            Documentación requerida
          </h2>
          <p className="text-sm text-gray-600 mb-4">
            Archivos que comercial u operaciones revisan para validar datos antes de generar el pase de caja. Formatos:
            PDF, JPG o PNG (máx. 10 MB por archivo). Puedes reemplazar un archivo eligiendo otro antes de enviar.
          </p>
          <div className="rounded-lg border border-amber-100 bg-amber-50/60 px-4 py-3 text-sm text-amber-950 mb-4">
            <strong className="font-semibold">Descuento:</strong> si aplicaste un código, también adjunta el acuse de
            solicitud de descuento (aparece en obligatorios).
          </div>
          {docDefsLoading ? (
            <p className="text-sm text-gray-500">Cargando lista de documentos…</p>
          ) : (
            <div className="space-y-6">
              {docPreviewLists.required.length > 0 && (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-3">Obligatorios</p>
                  <div className="space-y-4">
                    {docPreviewLists.required.map((d) => {
                      const inputId = `pending-${d.code}`;
                      const selected = pendingFiles[d.code];
                      const file = selected instanceof File ? selected : undefined;
                      return (
                        <div key={d.id} className="rounded-lg border border-gray-100 bg-gray-50/80 p-4">
                          <div className="mb-2">
                            <p className="font-medium text-gray-900">{d.label}</p>
                            <p className="text-xs text-gray-500">{d.code}</p>
                          </div>
                          <label
                            htmlFor={inputId}
                            onDragOver={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                            }}
                            onDrop={(e) => {
                              e.preventDefault();
                              const f = e.dataTransfer.files[0];
                              if (f)
                                setPendingFiles((prev) => ({
                                  ...prev,
                                  [d.code]: f,
                                }));
                            }}
                            className="flex flex-col items-center justify-center gap-2 border-2 border-dashed border-gray-200 rounded-lg px-4 py-6 cursor-pointer hover:border-blue-400 hover:bg-blue-50/40 transition"
                          >
                            <FileUp className="w-7 h-7 text-gray-400" />
                            <span className="text-sm text-gray-700 text-center">
                              Arrastra o haz clic para elegir archivo
                            </span>
                            {file && (
                              <span className="text-xs text-emerald-700 font-medium break-all max-w-full">
                                Seleccionado: {file.name}
                              </span>
                            )}
                            <input
                              id={inputId}
                              type="file"
                              accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                              className="hidden"
                              onChange={(e) => {
                                const f = e.target.files?.[0];
                                if (f)
                                  setPendingFiles((prev) => ({
                                    ...prev,
                                    [d.code]: f,
                                  }));
                                e.target.value = '';
                              }}
                            />
                          </label>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
              {docPreviewLists.optional.length > 0 && (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-3">Opcionales</p>
                  <div className="space-y-4">
                    {docPreviewLists.optional.map((d) => {
                      if (d.code === 'OTRO') {
                        const list = Array.isArray(pendingFiles.OTRO) ? pendingFiles.OTRO : [];
                        return (
                          <div key={d.id} className="rounded-lg border border-dashed border-gray-200 p-4">
                            <div className="mb-2">
                              <p className="font-medium text-gray-900">{d.label}</p>
                              <p className="text-xs text-gray-500">Puedes adjuntar varios archivos.</p>
                            </div>
                            <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-slate-100 px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-200">
                              <FileUp className="w-4 h-4" />
                              Agregar archivo
                              <input
                                type="file"
                                accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                                className="hidden"
                                onChange={(e) => {
                                  const f = e.target.files?.[0];
                                  if (f) {
                                    setPendingFiles((prev) => {
                                      const prevList = Array.isArray(prev.OTRO) ? prev.OTRO : [];
                                      return { ...prev, OTRO: [...prevList, f] };
                                    });
                                  }
                                  e.target.value = '';
                                }}
                              />
                            </label>
                            {list.length > 0 && (
                              <ul className="mt-3 space-y-1 text-sm text-gray-700">
                                {list.map((f, i) => (
                                  <li key={`${f.name}-${i}`} className="flex items-center justify-between gap-2">
                                    <span className="truncate">{f.name}</span>
                                    <button
                                      type="button"
                                      className="text-red-600 text-xs shrink-0"
                                      onClick={() =>
                                        setPendingFiles((prev) => {
                                          const prevList = Array.isArray(prev.OTRO) ? [...prev.OTRO] : [];
                                          prevList.splice(i, 1);
                                          return { ...prev, OTRO: prevList };
                                        })
                                      }
                                    >
                                      Quitar
                                    </button>
                                  </li>
                                ))}
                              </ul>
                            )}
                          </div>
                        );
                      }
                      const inputId = `pending-opt-${d.code}`;
                      const selected = pendingFiles[d.code];
                      const file = selected instanceof File ? selected : undefined;
                      return (
                        <div key={d.id} className="rounded-lg border border-dashed border-gray-200 p-4">
                          <div className="mb-2">
                            <p className="font-medium text-gray-900">{d.label}</p>
                            <p className="text-xs text-gray-500">{d.code}</p>
                          </div>
                          <label
                            htmlFor={inputId}
                            className="flex flex-col items-center justify-center gap-2 border-2 border-dashed border-gray-200 rounded-lg px-4 py-5 cursor-pointer hover:border-blue-400 hover:bg-blue-50/40 transition"
                          >
                            <span className="text-sm text-gray-700">Opcional — arrastra o elige archivo</span>
                            {file && (
                              <span className="text-xs text-emerald-700 font-medium break-all">{file.name}</span>
                            )}
                            <input
                              id={inputId}
                              type="file"
                              accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                              className="hidden"
                              onChange={(e) => {
                                const f = e.target.files?.[0];
                                if (f)
                                  setPendingFiles((prev) => ({
                                    ...prev,
                                    [d.code]: f,
                                  }));
                                e.target.value = '';
                              }}
                            />
                          </label>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
              {docPreviewLists.required.length === 0 && docPreviewLists.optional.length === 0 && (
                <p className="text-sm text-gray-500">No hay definiciones de documentos configuradas.</p>
              )}
            </div>
          )}
        </section>

        {docUploadError && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-sm text-amber-950">
            {docUploadError}
          </div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-red-700">{error}</div>
          </div>
        )}

        <button
          type="submit"
          disabled={isSubmitting || docDefsLoading || !hasAllRequiredPendingFiles}
          className="w-full bg-blue-600 text-white py-4 rounded-lg font-bold hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition shadow-lg hover:shadow-xl text-lg"
        >
          {isSubmitting ? (
            <span className="flex items-center justify-center">
              <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                ></path>
              </svg>
              Enviando solicitud y documentos…
            </span>
          ) : (
            'Enviar solicitud con documentación'
          )}
        </button>

        <p className="text-xs text-gray-500 text-center mt-2">
          Se creará tu reserva, se subirán los archivos al expediente y, si todo es correcto, pasarás a la confirmación.
          Recibirás el correo con instrucciones de pago y el &ldquo;Pase de Caja&rdquo;.
        </p>
      </form>
    </div>
  );
}
