/**
 * Contratos API transversales (DTOs). Preferir tipos por feature cuando el dominio sea exclusivo.
 * Sesión server-side unificada: `AuthContext` en [features/auth/types.ts](src/frontend/features/auth/types.ts).
 */

/** Respuesta típica de GET /me (sesión staff/portal). */
export interface MeResponse {
  tenant_id: string;
  role: string | null;
  user_id: string;
}
