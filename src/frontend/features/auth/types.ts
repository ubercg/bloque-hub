/**
 * Auth domain types (frontend contract).
 */

export interface AuthUser {
  id: string;
  email: string;
  full_name?: string;
  role?: string;
}

/** Rol JWT/backend (string flexible; alinear con backend). */
export type Role = string;

/**
 * Resultado único de validación server-side (middleware, Server Actions, route handlers).
 */
export type AuthContext =
  | { isValid: false; reason: 'missing_token' | 'malformed' | 'expired' }
  | {
      isValid: true;
      userId: string;
      role: Role;
      tenantId?: string;
    };
