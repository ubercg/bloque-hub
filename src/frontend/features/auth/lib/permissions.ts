/**
 * Permisos del back-office alineados con backend app/core/permissions.py.
 * Define qué roles pueden acceder a cada módulo del portal de administración.
 */

export const CAN_ACCESS_CRM = ['COMMERCIAL', 'SUPERADMIN'] as const;
export const CAN_ACCESS_OPERATIONS = ['OPERATIONS', 'SUPERADMIN'] as const;
export const CAN_ACCESS_FINANCE = ['FINANCE', 'SUPERADMIN'] as const;
export const CAN_ACCESS_SUPERADMIN = ['SUPERADMIN'] as const;
/** Catálogo: espacios, Matterport e imágenes promocionales por sede (tenant). */
export const CAN_ACCESS_SPACES_ADMIN = ['SUPERADMIN'] as const;
export const CAN_ACCESS_STAFF_MONITOR = ['COMMERCIAL', 'OPERATIONS', 'FINANCE', 'SUPERADMIN'] as const;
export const CAN_ACCESS_PRICING_CONFIG = ['COMMERCIAL', 'FINANCE', 'SUPERADMIN'] as const;
export const CAN_ACCESS_DISCOUNT_CONFIG = ['FINANCE', 'SUPERADMIN'] as const;

export type StaffRole = 'COMMERCIAL' | 'OPERATIONS' | 'FINANCE' | 'SUPERADMIN';

const ROLE_MODULE_MAP: Record<StaffRole, readonly string[]> = {
  COMMERCIAL: ['crm', 'operations', 'occupancy'],
  OPERATIONS: ['operations', 'occupancy'],
  FINANCE: ['finance', 'operations', 'occupancy', 'pricing', 'discounts'],
  SUPERADMIN: ['crm', 'operations', 'finance', 'occupancy', 'pricing', 'discounts', 'settings', 'spaces'],
};

/**
 * Devuelve los slugs de módulos a los que el rol tiene acceso (para el sidebar).
 */
export function getModulesForRole(role: string | undefined): string[] {
  if (!role || !(role in ROLE_MODULE_MAP)) return [];
  return [...ROLE_MODULE_MAP[role as StaffRole]];
}

/**
 * Comprueba si el rol puede acceder al módulo dado.
 */
export function canAccessModule(role: string | undefined, module: string): boolean {
  const modules = getModulesForRole(role);
  return modules.includes(module);
}

/**
 * Roles permitidos por ruta de admin (path segment después de /admin).
 */
export const ADMIN_ROUTE_ROLES: Record<string, readonly string[]> = {
  crm: CAN_ACCESS_CRM,
  /** Control Center: operaciones + comercial/finanzas (pase de caja, expediente, timeline). */
  operations: ['OPERATIONS', 'COMMERCIAL', 'FINANCE', 'SUPERADMIN'] as const,
  finance: CAN_ACCESS_FINANCE,
  occupancy: CAN_ACCESS_STAFF_MONITOR,
  pricing: CAN_ACCESS_PRICING_CONFIG,
  discounts: CAN_ACCESS_DISCOUNT_CONFIG,
  settings: CAN_ACCESS_SUPERADMIN,
  spaces: CAN_ACCESS_SPACES_ADMIN,
};

export function getAllowedRolesForAdminPath(pathSegment: string): readonly string[] {
  return ADMIN_ROUTE_ROLES[pathSegment] ?? [];
}
