/**
 * Public API — import from `@/features/auth` only (app / cross-feature).
 */

export type { AuthUser, AuthContext, Role } from './types';

export {
  useAuthStore,
  hasAuthCookie,
} from './store/auth.store';

export {
  CAN_ACCESS_CRM,
  CAN_ACCESS_OPERATIONS,
  CAN_ACCESS_FINANCE,
  CAN_ACCESS_SUPERADMIN,
  CAN_ACCESS_SPACES_ADMIN,
  CAN_ACCESS_STAFF_MONITOR,
  CAN_ACCESS_PRICING_CONFIG,
  CAN_ACCESS_DISCOUNT_CONFIG,
  getModulesForRole,
  canAccessModule,
  ADMIN_ROUTE_ROLES,
  getAllowedRolesForAdminPath,
} from './lib/permissions';
export type { StaffRole } from './lib/permissions';

export { loginWithCredentials } from './lib/auth.service';
export type { LoginResponse } from './lib/auth.service';

export { default as AdminHeader } from './components/AdminHeader';
export { default as RoleGuard } from './components/RoleGuard';

export { AdminShell } from './containers/AdminShell';
export { useStaffRoleHydration } from './hooks/useStaffRoleHydration';
