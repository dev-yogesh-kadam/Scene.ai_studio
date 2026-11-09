// Signing in: the studio's own sign-in (api/auth.py), which keeps the session in a cookie for the site and the studio.
import { ApiError, postJson, request } from './client';
import type { Me, User } from '@/types/api';

export function login(email: string, password: string, code?: string) {
  return postJson<User>('/api/auth/login', { email, password, ...(code ? { code } : {}) });
}

export function me() {
  return request<Me>('/api/auth/me');
}

export function logout() {
  return postJson<{ ok: true }>('/api/auth/logout', {});
}

/** Whether a failed sign-in is asking for the 6-digit code rather than refusing the password. */
export function needsCode(error: unknown) {
  return error instanceof ApiError && !!(error.body as { mfa_required?: boolean } | null)?.mfa_required;
}
