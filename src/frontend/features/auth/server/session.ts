/**
 * Server-side auth helpers (Edge-safe): JWT decode without verify, role checks.
 * Single source of truth for middleware and future Server Actions / route handlers.
 */

export const STAFF_ROLES = ['COMMERCIAL', 'OPERATIONS', 'FINANCE', 'SUPERADMIN'] as const;

/**
 * Decode JWT payload without signature verification (Edge Runtime compatible).
 * Returns null if the token is malformed.
 */
export function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const payload = JSON.parse(atob(base64));
    return payload;
  } catch {
    return null;
  }
}

/** True solo si `exp` existe y ya venció (alineado con middleware histórico). */
export function isJwtExpired(payload: Record<string, unknown>): boolean {
  if (typeof payload.exp !== 'number') return false;
  return payload.exp * 1000 < Date.now();
}

export function getRoleFromPayload(payload: Record<string, unknown> | null): string | undefined {
  const role = payload?.role;
  return typeof role === 'string' ? role : undefined;
}

export function isStaffRole(role: string | undefined): boolean {
  return STAFF_ROLES.includes(role as (typeof STAFF_ROLES)[number]);
}
