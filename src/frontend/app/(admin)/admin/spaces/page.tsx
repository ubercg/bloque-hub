'use client';

/**
 * SuperAdmin: CRUD de espacios por sede (tenant).
 * POST/PATCH/DELETE /api/spaces con ?tenant_id= cuando el JWT es SUPERADMIN.
 * Imágenes promo: POST /api/spaces/promo-media/upload → URL pública /api/media/space-promo/...
 */

import { useEffect, useRef, useState } from 'react';
import useSWR from 'swr';
import { toast } from 'sonner';

import { CAN_ACCESS_SPACES_ADMIN, RoleGuard } from '@/features/auth';
import apiClient from '@/lib/http/apiClient';

interface Tenant {
  id: string;
  name: string;
  slug: string;
}

type BookingMode = 'QUOTE_REQUIRED' | 'SEMI_DIRECT';

interface SpaceRow {
  id: string;
  tenant_id: string;
  name: string;
  slug: string;
  booking_mode: BookingMode;
  capacidad_maxima: number;
  precio_por_hora: number;
  ttl_minutos: number;
  is_active: boolean;
  piso?: number | null;
  descripcion?: string | null;
  matterport_url?: string | null;
  promo_hero_url?: string | null;
  promo_gallery_urls?: string[] | null;
  amenidades?: string[] | null;
}

const fetcher = (url: string) => apiClient.get(url).then((r) => r.data);

/** URL absoluta para <img src> cuando NEXT_PUBLIC_API_URL termina en /api. */
function resolveMediaUrl(path: string): string {
  if (!path) return '';
  if (path.startsWith('http://') || path.startsWith('https://')) return path;
  const base = process.env.NEXT_PUBLIC_API_URL || '';
  if (base && path.startsWith('/api')) {
    return base.replace(/\/api\/?$/, '') + path;
  }
  return path;
}

const emptyForm = () => ({
  name: '',
  slug: '',
  booking_mode: 'QUOTE_REQUIRED' as BookingMode,
  capacidad_maxima: '0',
  precio_por_hora: '0',
  ttl_minutos: '1440',
  piso: '',
  descripcion: '',
  is_active: true,
  matterport_url: '',
  promo_hero_url: '',
  promo_gallery: '',
  amenidades: '',
});

function SpacesAdminContent() {
  const { data: tenants = [] } = useSWR<Tenant[]>('/tenants', fetcher);
  const [tenantId, setTenantId] = useState<string | null>(null);

  const spacesKey = tenantId ? `/spaces?tenant_id=${encodeURIComponent(tenantId)}` : null;
  const { data: spaces = [], mutate: mutateSpaces } = useSWR<SpaceRow[]>(spacesKey, fetcher);

  const [createOpen, setCreateOpen] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [uploadingHero, setUploadingHero] = useState(false);
  const [uploadingGallery, setUploadingGallery] = useState(false);
  const heroFileRef = useRef<HTMLInputElement>(null);
  const galleryFileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (tenants.length && !tenantId) {
      setTenantId(tenants[0].id);
    }
  }, [tenants, tenantId]);

  const openCreate = () => {
    setForm(emptyForm());
    setCreateOpen(true);
  };

  const openEdit = (s: SpaceRow) => {
    setEditId(s.id);
    setForm({
      name: s.name,
      slug: s.slug,
      booking_mode: s.booking_mode,
      capacidad_maxima: String(s.capacidad_maxima),
      precio_por_hora: String(s.precio_por_hora),
      ttl_minutos: String(s.ttl_minutos),
      piso: s.piso != null ? String(s.piso) : '',
      descripcion: s.descripcion ?? '',
      is_active: s.is_active,
      matterport_url: s.matterport_url ?? '',
      promo_hero_url: s.promo_hero_url ?? '',
      promo_gallery: (s.promo_gallery_urls ?? []).join(', '),
      amenidades: (s.amenidades ?? []).join(', '),
    });
  };

  const parseGallery = (raw: string) =>
    raw
      .split(/[,;\n]/)
      .map((x) => x.trim())
      .filter(Boolean);

  const parseAmenidades = (raw: string) =>
    raw
      .split(',')
      .map((x) => x.trim())
      .filter(Boolean);

  const promoUploadQuery = () =>
    tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : '';

  const uploadPromoFile = async (file: File) => {
    if (!tenantId) {
      toast.error('Elegí una sede antes de subir imágenes');
      throw new Error('no tenant');
    }
    const fd = new FormData();
    fd.append('file', file);
    const { data } = await apiClient.post<{ url: string }>(
      `/spaces/promo-media/upload${promoUploadQuery()}`,
      fd
    );
    return data.url;
  };

  const onPickHeroFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setUploadingHero(true);
    try {
      const url = await uploadPromoFile(file);
      setForm((f) => ({ ...f, promo_hero_url: url }));
      toast.success('Imagen hero cargada');
    } catch (err) {
      toastApiError(err, 'No se pudo subir la imagen');
    } finally {
      setUploadingHero(false);
    }
  };

  const onPickGalleryFiles = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files ? Array.from(e.target.files) : [];
    e.target.value = '';
    if (!files.length) return;
    setUploadingGallery(true);
    try {
      const urls: string[] = [];
      for (const file of files) {
        urls.push(await uploadPromoFile(file));
      }
      setForm((f) => {
        const existing = parseGallery(f.promo_gallery);
        const merged = [...existing, ...urls].filter(Boolean);
        return { ...f, promo_gallery: merged.join(', ') };
      });
      toast.success(urls.length === 1 ? 'Imagen añadida a la galería' : 'Imágenes añadidas a la galería');
    } catch (err) {
      toastApiError(err, 'No se pudo subir la galería');
    } finally {
      setUploadingGallery(false);
    }
  };

  const submitCreate = async () => {
    if (!tenantId) return;
    const cap = Number(form.capacidad_maxima);
    const precio = Number(form.precio_por_hora);
    const ttl = Number(form.ttl_minutos);
    if (!form.name.trim() || !form.slug.trim()) {
      toast.error('Nombre y slug son obligatorios');
      return;
    }
    if (Number.isNaN(cap) || cap < 0 || Number.isNaN(precio) || precio < 0 || Number.isNaN(ttl) || ttl < 1) {
      toast.error('Revisá capacidad, precio y TTL');
      return;
    }
    let piso: number | null = null;
    if (form.piso.trim() !== '') {
      const p = Number(form.piso);
      if (Number.isNaN(p) || p < 0 || p > 7) {
        toast.error('Piso debe ser 0–7 o vacío');
        return;
      }
      piso = p;
    }
    const galleryUrls = parseGallery(form.promo_gallery);
    const amenidades = parseAmenidades(form.amenidades);
    setSaving(true);
    try {
      await apiClient.post(`/spaces?tenant_id=${encodeURIComponent(tenantId)}`, {
        name: form.name.trim(),
        slug: form.slug.trim().toLowerCase(),
        booking_mode: form.booking_mode,
        capacidad_maxima: cap,
        precio_por_hora: precio,
        ttl_minutos: ttl,
        piso,
        descripcion: form.descripcion.trim() || null,
        is_active: form.is_active,
        matterport_url: form.matterport_url.trim() || null,
        promo_hero_url: form.promo_hero_url.trim() || null,
        promo_gallery_urls: galleryUrls.length ? galleryUrls : null,
        amenidades: amenidades.length ? amenidades : null,
      });
      toast.success('Espacio creado');
      setCreateOpen(false);
      await mutateSpaces();
    } catch (e: unknown) {
      toastApiError(e, 'No se pudo crear');
    } finally {
      setSaving(false);
    }
  };

  const submitEdit = async () => {
    if (!editId) return;
    const cap = Number(form.capacidad_maxima);
    const precio = Number(form.precio_por_hora);
    const ttl = Number(form.ttl_minutos);
    if (!form.name.trim() || !form.slug.trim()) {
      toast.error('Nombre y slug son obligatorios');
      return;
    }
    if (Number.isNaN(cap) || cap < 0 || Number.isNaN(precio) || precio < 0 || Number.isNaN(ttl) || ttl < 1) {
      toast.error('Revisá capacidad, precio y TTL');
      return;
    }
    let piso: number | null = null;
    if (form.piso.trim() !== '') {
      const p = Number(form.piso);
      if (Number.isNaN(p) || p < 0 || p > 7) {
        toast.error('Piso debe ser 0–7 o vacío');
        return;
      }
      piso = p;
    }
    const galleryUrls = parseGallery(form.promo_gallery);
    const amenidades = parseAmenidades(form.amenidades);
    setSaving(true);
    try {
      await apiClient.patch(`/spaces/${editId}`, {
        name: form.name.trim(),
        slug: form.slug.trim().toLowerCase(),
        booking_mode: form.booking_mode,
        capacidad_maxima: cap,
        precio_por_hora: precio,
        ttl_minutos: ttl,
        piso,
        descripcion: form.descripcion.trim() || null,
        is_active: form.is_active,
        matterport_url: form.matterport_url.trim() || null,
        promo_hero_url: form.promo_hero_url.trim() || null,
        promo_gallery_urls: galleryUrls.length ? galleryUrls : null,
        amenidades: amenidades.length ? amenidades : null,
      });
      toast.success('Espacio actualizado');
      setEditId(null);
      await mutateSpaces();
    } catch (e: unknown) {
      toastApiError(e, 'No se pudo guardar');
    } finally {
      setSaving(false);
    }
  };

  const submitDelete = async () => {
    if (!deleteId) return;
    setSaving(true);
    try {
      await apiClient.delete(`/spaces/${deleteId}`);
      toast.success('Espacio eliminado');
      setDeleteId(null);
      await mutateSpaces();
    } catch (e: unknown) {
      toastApiError(e, 'No se pudo eliminar');
    } finally {
      setSaving(false);
    }
  };

  const selectedTenant = tenants.find((t) => t.id === tenantId);

  return (
    <div className="space-y-6 max-w-5xl">
      <h1 className="text-xl font-bold text-gray-900">Espacios</h1>
      <p className="text-sm text-gray-600">
        CRUD de espacios por sede. Solo SuperAdmin. El slug debe ser único dentro de la sede.
      </p>

      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm flex items-center gap-2">
          <span className="text-gray-600">Sede</span>
          <select
            className="border border-gray-300 rounded-lg px-3 py-2 min-w-[220px]"
            value={tenantId ?? ''}
            onChange={(e) => setTenantId(e.target.value || null)}
          >
            {tenants.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name} ({t.slug})
              </option>
            ))}
          </select>
        </label>
        {selectedTenant && (
          <button
            type="button"
            onClick={openCreate}
            className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm hover:bg-blue-700"
          >
            Nuevo espacio
          </button>
        )}
      </div>

      <div className="border border-gray-200 rounded-lg overflow-hidden overflow-x-auto">
        <table className="w-full text-sm text-left min-w-[640px]">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-4 py-2 font-medium text-gray-700">Nombre</th>
              <th className="px-4 py-2 font-medium text-gray-700">Slug</th>
              <th className="px-4 py-2 font-medium text-gray-700">$/h</th>
              <th className="px-4 py-2 font-medium text-gray-700">Cap.</th>
              <th className="px-4 py-2 font-medium text-gray-700">Modo</th>
              <th className="px-4 py-2 font-medium text-gray-700">Activo</th>
              <th className="px-4 py-2 font-medium text-gray-700 text-right">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {spaces.map((s) => (
              <tr key={s.id} className="border-b border-gray-100 hover:bg-gray-50">
                <td className="px-4 py-2 font-medium text-gray-900">{s.name}</td>
                <td className="px-4 py-2 font-mono text-xs text-gray-600">{s.slug}</td>
                <td className="px-4 py-2">{Number(s.precio_por_hora).toLocaleString('es-MX')}</td>
                <td className="px-4 py-2">{s.capacidad_maxima}</td>
                <td className="px-4 py-2 text-xs">{s.booking_mode}</td>
                <td className="px-4 py-2">{s.is_active ? 'Sí' : 'No'}</td>
                <td className="px-4 py-2 text-right space-x-2 whitespace-nowrap">
                  <button
                    type="button"
                    className="text-blue-600 hover:underline"
                    onClick={() => openEdit(s)}
                  >
                    Editar
                  </button>
                  <button
                    type="button"
                    className="text-red-600 hover:underline"
                    onClick={() => setDeleteId(s.id)}
                  >
                    Eliminar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {tenantId && spaces.length === 0 && (
          <div className="p-6 text-center text-gray-500 text-sm">
            No hay espacios en esta sede. Creá uno con &quot;Nuevo espacio&quot;.
          </div>
        )}
      </div>

      {(createOpen || editId) && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 overflow-y-auto"
          role="dialog"
          aria-modal="true"
        >
          <div className="bg-white rounded-xl shadow-lg max-w-lg w-full p-4 space-y-3 my-8 max-h-[90vh] overflow-y-auto">
            <h3 className="font-semibold text-gray-900">
              {createOpen ? 'Nuevo espacio' : 'Editar espacio'}
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <label className="text-sm sm:col-span-2">
                <span className="text-gray-600">Nombre</span>
                <input
                  className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2"
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                />
              </label>
              <label className="text-sm sm:col-span-2">
                <span className="text-gray-600">Slug (único en la sede)</span>
                <input
                  className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 font-mono text-sm"
                  value={form.slug}
                  onChange={(e) => setForm((f) => ({ ...f, slug: e.target.value }))}
                />
              </label>
              <label className="text-sm">
                <span className="text-gray-600">Modo reserva</span>
                <select
                  className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2"
                  value={form.booking_mode}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, booking_mode: e.target.value as BookingMode }))
                  }
                >
                  <option value="QUOTE_REQUIRED">Cotización (QUOTE_REQUIRED)</option>
                  <option value="SEMI_DIRECT">Semi-directo (SEMI_DIRECT)</option>
                </select>
              </label>
              <label className="text-sm">
                <span className="text-gray-600">Activo</span>
                <div className="mt-2">
                  <input
                    type="checkbox"
                    checked={form.is_active}
                    onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
                  />
                </div>
              </label>
              <label className="text-sm">
                <span className="text-gray-600">Capacidad máx.</span>
                <input
                  type="number"
                  min={0}
                  className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2"
                  value={form.capacidad_maxima}
                  onChange={(e) => setForm((f) => ({ ...f, capacidad_maxima: e.target.value }))}
                />
              </label>
              <label className="text-sm">
                <span className="text-gray-600">Precio / hora (MXN)</span>
                <input
                  type="number"
                  min={0}
                  step={0.01}
                  className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2"
                  value={form.precio_por_hora}
                  onChange={(e) => setForm((f) => ({ ...f, precio_por_hora: e.target.value }))}
                />
              </label>
              <label className="text-sm">
                <span className="text-gray-600">TTL minutos</span>
                <input
                  type="number"
                  min={1}
                  className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2"
                  value={form.ttl_minutos}
                  onChange={(e) => setForm((f) => ({ ...f, ttl_minutos: e.target.value }))}
                />
              </label>
              <label className="text-sm">
                <span className="text-gray-600">Piso (0–7, vacío = sin dato)</span>
                <input
                  className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2"
                  value={form.piso}
                  onChange={(e) => setForm((f) => ({ ...f, piso: e.target.value }))}
                />
              </label>
              <label className="text-sm sm:col-span-2">
                <span className="text-gray-600">Descripción</span>
                <textarea
                  className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm min-h-[72px]"
                  value={form.descripcion}
                  onChange={(e) => setForm((f) => ({ ...f, descripcion: e.target.value }))}
                />
              </label>
              <label className="text-sm sm:col-span-2">
                <span className="text-gray-600">Amenidades (separadas por coma)</span>
                <input
                  className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
                  value={form.amenidades}
                  onChange={(e) => setForm((f) => ({ ...f, amenidades: e.target.value }))}
                  placeholder="WiFi, Proyector"
                />
              </label>
              <label className="text-sm sm:col-span-2">
                <span className="text-gray-600">Matterport (URL)</span>
                <input
                  className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 font-mono text-xs"
                  value={form.matterport_url}
                  onChange={(e) => setForm((f) => ({ ...f, matterport_url: e.target.value }))}
                />
              </label>
              <div className="text-sm sm:col-span-2 space-y-2">
                <span className="text-gray-600 block">Imagen hero (tarjeta / ficha)</span>
                <div className="flex flex-wrap items-center gap-2">
                  <input
                    ref={heroFileRef}
                    type="file"
                    accept="image/jpeg,image/png,image/webp,image/gif"
                    className="hidden"
                    onChange={onPickHeroFile}
                  />
                  <button
                    type="button"
                    disabled={!tenantId || uploadingHero}
                    className="px-3 py-1.5 text-xs rounded-lg border border-gray-300 bg-white hover:bg-gray-50 disabled:opacity-50"
                    onClick={() => heroFileRef.current?.click()}
                  >
                    {uploadingHero ? 'Subiendo…' : 'Subir imagen'}
                  </button>
                  {form.promo_hero_url.trim() && (
                    <span className="text-xs text-gray-500 truncate max-w-[200px]" title={form.promo_hero_url}>
                      {form.promo_hero_url}
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap gap-3 items-start">
                  {form.promo_hero_url.trim() ? (
                    <img
                      src={resolveMediaUrl(form.promo_hero_url.trim())}
                      alt="Vista previa hero"
                      className="max-h-28 rounded-lg border border-gray-200 object-cover"
                    />
                  ) : null}
                </div>
                <input
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 font-mono text-xs"
                  value={form.promo_hero_url}
                  onChange={(e) => setForm((f) => ({ ...f, promo_hero_url: e.target.value }))}
                  placeholder="URL o ruta (p. ej. /api/media/space-promo/… tras subir)"
                />
              </div>
              <div className="text-sm sm:col-span-2 space-y-2">
                <span className="text-gray-600 block">Galería (rutas o URLs, separadas por coma)</span>
                <div className="flex flex-wrap items-center gap-2">
                  <input
                    ref={galleryFileRef}
                    type="file"
                    accept="image/jpeg,image/png,image/webp,image/gif"
                    multiple
                    className="hidden"
                    onChange={onPickGalleryFiles}
                  />
                  <button
                    type="button"
                    disabled={!tenantId || uploadingGallery}
                    className="px-3 py-1.5 text-xs rounded-lg border border-gray-300 bg-white hover:bg-gray-50 disabled:opacity-50"
                    onClick={() => galleryFileRef.current?.click()}
                  >
                    {uploadingGallery ? 'Subiendo…' : 'Subir imágenes a la galería'}
                  </button>
                  <span className="text-xs text-gray-500">
                    Se añaden al final del texto; podés editar o pegar URLs externas.
                  </span>
                </div>
                <textarea
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 font-mono text-xs min-h-[64px]"
                  value={form.promo_gallery}
                  onChange={(e) => setForm((f) => ({ ...f, promo_gallery: e.target.value }))}
                  placeholder="https://…, /api/media/space-promo/…"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                className="px-3 py-1.5 text-sm rounded-lg border border-gray-300"
                onClick={() => {
                  setCreateOpen(false);
                  setEditId(null);
                }}
              >
                Cancelar
              </button>
              <button
                type="button"
                disabled={saving}
                className="px-3 py-1.5 text-sm rounded-lg bg-blue-600 text-white disabled:opacity-50"
                onClick={createOpen ? submitCreate : submitEdit}
              >
                {createOpen ? 'Crear' : 'Guardar'}
              </button>
            </div>
          </div>
        </div>
      )}

      {deleteId && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/40"
          role="dialog"
          aria-modal="true"
        >
          <div className="bg-white rounded-xl shadow-lg max-w-md w-full p-4 space-y-3">
            <h3 className="font-semibold text-gray-900">¿Eliminar espacio?</h3>
            <p className="text-sm text-gray-600">
              Esta acción borra el espacio y datos relacionados según reglas de la base. No se puede
              deshacer.
            </p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                className="px-3 py-1.5 text-sm rounded-lg border border-gray-300"
                onClick={() => setDeleteId(null)}
              >
                Cancelar
              </button>
              <button
                type="button"
                disabled={saving}
                className="px-3 py-1.5 text-sm rounded-lg bg-red-600 text-white disabled:opacity-50"
                onClick={submitDelete}
              >
                Eliminar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function toastApiError(e: unknown, fallback: string) {
  const detail =
    e && typeof e === 'object' && 'response' in e
      ? (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      : undefined;
  const msg =
    typeof detail === 'string'
      ? detail
      : Array.isArray(detail)
        ? (detail as { msg?: string }[]).map((d) => d.msg ?? '').join(', ')
        : fallback;
  toast.error(msg);
}

export default function SpacesAdminPage() {
  return (
    <RoleGuard allowedRoles={CAN_ACCESS_SPACES_ADMIN}>
      <SpacesAdminContent />
    </RoleGuard>
  );
}
