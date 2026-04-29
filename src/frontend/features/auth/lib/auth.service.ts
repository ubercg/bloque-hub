/**
 * Auth API orchestration (I/O). Store must not call fetch directly.
 */

import apiClient from '@/lib/http/apiClient';

import type { AuthUser } from '../types';

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
  tenant_id: string;
}

export async function loginWithCredentials(
  email: string,
  password: string
): Promise<LoginResponse> {
  const { data } = await apiClient.post<LoginResponse>('/auth/login', { email, password });
  return data;
}
