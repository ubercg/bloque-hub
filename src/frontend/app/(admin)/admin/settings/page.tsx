'use client';

/**
 * Panel SuperAdmin: gestión de tenants y usuarios.
 * Requiere rol SUPERADMIN.
 */

import { useEffect, useState } from 'react';
import useSWR from 'swr';
import { toast } from 'sonner';

import { CAN_ACCESS_SUPERADMIN, RoleGuard } from '@/features/auth';
import apiClient from '@/lib/http/apiClient';

interface Tenant {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
  max_discount_threshold: number;
  created_at: string;
  updated_at: string;
}

interface User {
  id: string;
  tenant_id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

const fetcher = (url: string) => apiClient.get(url).then((r) => r.data);

const SEED_CMD =
  'poetry run python src/backend/scripts/seed_spaces_catalog_bloque.py --tenant-slug';

function SettingsContent() {
  const [selectedTenantId, setSelectedTenantId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createSlug, setCreateSlug] = useState('');
  const [createMaxDisc, setCreateMaxDisc] = useState('');
  const [saving, setSaving] = useState(false);

  const [editName, setEditName] = useState('');
  const [editSlug, setEditSlug] = useState('');
  const [editActive, setEditActive] = useState(true);
  const [editMaxDisc, setEditMaxDisc] = useState('');

  const { data: tenants = [], mutate: mutateTenants } = useSWR<Tenant[]>('/tenants', fetcher);
  const { data: users = [] } = useSWR<User[]>(
    selectedTenantId ? `/tenants/${selectedTenantId}/users` : null,
    fetcher
  );

  const selectedTenant = tenants.find((t) => t.id === selectedTenantId);

  useEffect(() => {
    if (selectedTenant) {
      setEditName(selectedTenant.name);
      setEditSlug(selectedTenant.slug);
      setEditActive(selectedTenant.is_active);
      setEditMaxDisc(String(selectedTenant.max_discount_threshold ?? 0));
    }
  }, [selectedTenant]);

  const openCreate = () => {
    setCreateName('');
    setCreateSlug('');
    setCreateMaxDisc('');
    setCreateOpen(true);
  };

  const submitCreate = async () => {
    const slug = createSlug.trim().toLowerCase();
    const payload: { name: string; slug: string; max_discount_threshold?: number } = {
      name: createName.trim(),
      slug,
    };
    if (createMaxDisc.trim() !== '') {
      const n = Number(createMaxDisc);
      if (Number.isNaN(n) || n < 0 || n > 100) {
        toast.error('Umbral de descuento debe ser un número entre 0 y 100');
        return;
      }
      payload.max_discount_threshold = n;
    }
    if (!payload.name || !payload.slug) {
      toast.error('Nombre y slug son obligatorios');
      return;
    }
    setSaving(true);
    try {
      await apiClient.post('/tenants', payload);
      toast.success('Tenant creado');
      setCreateOpen(false);
      await mutateTenants();
    } catch (e: unknown) {
      const detail =
        e && typeof e === 'object' && 'response' in e
          ? (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
          : undefined;
      const msg =
        typeof detail === 'string'
          ? detail
          : Array.isArray(detail)
            ? detail.map((d) => (d as { msg?: string }).msg).join(', ')
            : 'No se pudo crear el tenant';
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const submitEdit = async () => {
    if (!selectedTenantId) return;
    const payload: {
      name?: string;
      slug?: string;
      is_active?: boolean;
      max_discount_threshold?: number;
    } = {
      name: editName.trim(),
      slug: editSlug.trim().toLowerCase(),
      is_active: editActive,
    };
    const n = Number(editMaxDisc);
    if (Number.isNaN(n) || n < 0 || n > 100) {
      toast.error('Umbral de descuento debe ser un número entre 0 y 100');
      return;
    }
    payload.max_discount_threshold = n;
    setSaving(true);
    try {
      await apiClient.patch(`/tenants/${selectedTenantId}`, payload);
      toast.success('Tenant actualizado');
      await mutateTenants();
    } catch (e: unknown) {
      const detail =
        e && typeof e === 'object' && 'response' in e
          ? (e as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
          : undefined;
      const msg = typeof detail === 'string' ? detail : 'No se pudo guardar';
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const copySeedCommand = async () => {
    if (!selectedTenant?.slug) return;
    const line = `${SEED_CMD} ${selectedTenant.slug}`;
    try {
      await navigator.clipboard.writeText(line);
      toast.success('Comando copiado al portapapeles');
    } catch {
      toast.error('No se pudo copiar');
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-gray-900">Ajustes (SuperAdmin)</h1>
      <p className="text-sm text-gray-600">
        Gestión de tenants y usuarios. Solo visible para rol SuperAdmin. El borrado físico de tenants
        no está disponible (cascade en base de datos); podés desactivar un tenant con el interruptor
        de Activo.
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-lg font-semibold text-gray-800">Tenants</h2>
            <button
              type="button"
              onClick={openCreate}
              className="text-sm px-3 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700"
            >
              Nuevo tenant
            </button>
          </div>
          <div className="border border-gray-200 rounded-lg overflow-hidden">
            <ul className="divide-y divide-gray-100 max-h-[min(420px,50vh)] overflow-y-auto">
              {tenants.map((t) => (
                <li
                  key={t.id}
                  className={`p-3 cursor-pointer hover:bg-gray-50 ${
                    selectedTenantId === t.id ? 'bg-blue-50 border-l-4 border-blue-600' : ''
                  }`}
                  onClick={() => setSelectedTenantId(t.id)}
                >
                  <p className="font-medium text-gray-900">{t.name}</p>
                  <p className="text-xs text-gray-500 font-mono">{t.slug}</p>
                  <p className="text-xs text-gray-500 mt-1">
                    {t.is_active ? 'Activo' : 'Inactivo'} · umbral desc. {t.max_discount_threshold}%
                  </p>
                </li>
              ))}
            </ul>
            {tenants.length === 0 && (
              <div className="p-4 text-center text-gray-500 text-sm">No hay tenants</div>
            )}
          </div>

          {createOpen && (
            <div
              className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
              role="dialog"
              aria-modal="true"
              aria-labelledby="create-tenant-title"
            >
              <div className="bg-white rounded-xl shadow-lg max-w-md w-full p-4 space-y-3">
                <h3 id="create-tenant-title" className="font-semibold text-gray-900">
                  Nuevo tenant
                </h3>
                <label className="block text-sm">
                  <span className="text-gray-600">Nombre</span>
                  <input
                    className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2"
                    value={createName}
                    onChange={(e) => setCreateName(e.target.value)}
                    placeholder="Ej. Municipio BLOQUE"
                  />
                </label>
                <label className="block text-sm">
                  <span className="text-gray-600">Slug</span>
                  <input
                    className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 font-mono text-sm"
                    value={createSlug}
                    onChange={(e) => setCreateSlug(e.target.value)}
                    placeholder="bloque-hub"
                  />
                  <span className="text-xs text-gray-500">
                    Solo minúsculas, números y guiones. Coincide con{' '}
                    <code className="bg-gray-100 px-1 rounded">--tenant-slug</code> del seed de
                    espacios.
                  </span>
                </label>
                <label className="block text-sm">
                  <span className="text-gray-600">Umbral máx. descuento (%)</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step={0.01}
                    className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2"
                    value={createMaxDisc}
                    onChange={(e) => setCreateMaxDisc(e.target.value)}
                    placeholder="0 (opcional)"
                  />
                </label>
                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    className="px-3 py-1.5 text-sm rounded-lg border border-gray-300"
                    onClick={() => setCreateOpen(false)}
                  >
                    Cancelar
                  </button>
                  <button
                    type="button"
                    disabled={saving}
                    className="px-3 py-1.5 text-sm rounded-lg bg-blue-600 text-white disabled:opacity-50"
                    onClick={submitCreate}
                  >
                    Crear
                  </button>
                </div>
              </div>
            </div>
          )}
        </section>

        <section className="space-y-4">
          <h2 className="text-lg font-semibold text-gray-800">
            Detalle {selectedTenant ? `— ${selectedTenant.name}` : ''}
          </h2>
          {selectedTenantId && selectedTenant ? (
            <div className="space-y-4 border border-gray-200 rounded-lg p-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <label className="text-sm">
                  <span className="text-gray-600">Nombre</span>
                  <input
                    className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                  />
                </label>
                <label className="text-sm">
                  <span className="text-gray-600">Slug</span>
                  <input
                    className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 font-mono text-sm"
                    value={editSlug}
                    onChange={(e) => setEditSlug(e.target.value)}
                  />
                </label>
                <label className="text-sm flex items-center gap-2 pt-6">
                  <input
                    type="checkbox"
                    checked={editActive}
                    onChange={(e) => setEditActive(e.target.checked)}
                  />
                  <span className="text-gray-700">Tenant activo</span>
                </label>
                <label className="text-sm">
                  <span className="text-gray-600">Umbral máx. descuento (%)</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step={0.01}
                    className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2"
                    value={editMaxDisc}
                    onChange={(e) => setEditMaxDisc(e.target.value)}
                  />
                </label>
              </div>
              <button
                type="button"
                disabled={saving}
                onClick={submitEdit}
                className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm hover:bg-emerald-700 disabled:opacity-50"
              >
                Guardar cambios
              </button>

              <div className="pt-2 border-t border-gray-100">
                <p className="text-sm font-medium text-gray-800 mb-1">Catálogo de espacios (seed)</p>
                <p className="text-xs text-gray-600 mb-2">
                  Tras crear el tenant, podés cargar espacios e inventario con el script (mismo slug):
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <code className="text-xs bg-gray-100 px-2 py-1 rounded break-all max-w-full">
                    {SEED_CMD} {selectedTenant.slug}
                  </code>
                  <button
                    type="button"
                    onClick={copySeedCommand}
                    className="text-xs px-2 py-1 rounded border border-gray-300 hover:bg-gray-50"
                  >
                    Copiar
                  </button>
                </div>
              </div>

              <div>
                <h3 className="text-sm font-semibold text-gray-800 mb-2">
                  Usuarios de este tenant
                </h3>
                <div className="border border-gray-200 rounded-lg overflow-hidden overflow-x-auto">
                  <table className="w-full text-sm text-left min-w-[320px]">
                    <thead className="bg-gray-50 border-b border-gray-200">
                      <tr>
                        <th className="px-4 py-2 font-medium text-gray-700">Email</th>
                        <th className="px-4 py-2 font-medium text-gray-700">Nombre</th>
                        <th className="px-4 py-2 font-medium text-gray-700">Rol</th>
                      </tr>
                    </thead>
                    <tbody>
                      {users.map((u) => (
                        <tr key={u.id} className="border-b border-gray-100">
                          <td className="px-4 py-2">{u.email}</td>
                          <td className="px-4 py-2">{u.full_name}</td>
                          <td className="px-4 py-2">{u.role}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {users.length === 0 && (
                    <div className="p-4 text-center text-gray-500 text-sm">
                      Sin usuarios en este tenant
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="border border-gray-200 rounded-lg p-6 text-center text-gray-500 text-sm">
              Seleccioná un tenant para editar o ver usuarios
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <RoleGuard allowedRoles={CAN_ACCESS_SUPERADMIN}>
      <SettingsContent />
    </RoleGuard>
  );
}
