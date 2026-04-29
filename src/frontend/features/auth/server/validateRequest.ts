import type { NextRequest } from 'next/server';

import type { AuthContext } from '../types';
import { decodeJwtPayload, getRoleFromPayload, isJwtExpired } from './session';

function userIdFromPayload(payload: Record<string, unknown>): string {
  const sub = payload.sub;
  if (typeof sub === 'string' && sub.length > 0) return sub;
  const uid = payload.user_id;
  if (typeof uid === 'string' && uid.length > 0) return uid;
  return '';
}

/**
 * Contrato único para cookie JWT en Edge: middleware y futuros handlers reutilizan esto.
 */
export function validateAuthFromNextRequest(request: NextRequest): AuthContext {
  const token = request.cookies.get('auth_token')?.value;
  if (!token) {
    return { isValid: false, reason: 'missing_token' };
  }

  const payload = decodeJwtPayload(token);
  if (!payload) {
    return { isValid: false, reason: 'malformed' };
  }

  if (isJwtExpired(payload)) {
    return { isValid: false, reason: 'expired' };
  }

  const role = getRoleFromPayload(payload) ?? '';
  const userId = userIdFromPayload(payload);
  const tenantRaw = payload.tenant_id;
  const tenantId = typeof tenantRaw === 'string' ? tenantRaw : undefined;

  return {
    isValid: true,
    userId: userId || 'unknown',
    role,
    tenantId,
  };
}
