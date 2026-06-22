import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

import { isStaffRole } from '@/features/auth/server/session';
import { validateAuthFromNextRequest } from '@/features/auth/server/validateRequest';

const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? '';

/**
 * Build a redirect URL that includes the configured basePath.
 * Next.js middleware does not auto-apply basePath to URLs built from request.url,
 * so without this a redirect to '/login' resolves to '/login' (404) instead of
 * '/bloque/login'. request.nextUrl.pathname already has basePath stripped.
 */
function redirectUrl(path: string, request: NextRequest): URL {
  return new URL(`${BASE_PATH}${path}`, request.url);
}

/**
 * Auth middleware: orquestación; validación vía validateAuthFromNextRequest → AuthContext.
 */
export function authMiddleware(request: NextRequest) {
  const ctx = validateAuthFromNextRequest(request);

  const isAuthPage =
    request.nextUrl.pathname.startsWith('/login') ||
    request.nextUrl.pathname.startsWith('/register');
  const isPublicPage =
    request.nextUrl.pathname === '/' || request.nextUrl.pathname.startsWith('/catalog');

  if (!ctx.isValid) {
    if (ctx.reason === 'missing_token') {
      if (!isAuthPage && !isPublicPage) {
        const loginUrl = redirectUrl('/login', request);
        loginUrl.searchParams.set('redirect', request.nextUrl.pathname);
        return NextResponse.redirect(loginUrl);
      }
      return NextResponse.next();
    }
    const response = NextResponse.redirect(redirectUrl('/login', request));
    response.cookies.delete('auth_token');
    return response;
  }

  const role = ctx.role;
  const staff = isStaffRole(role);

  if (isAuthPage) {
    const target = staff ? '/admin/dashboard' : '/my-events';
    return NextResponse.redirect(redirectUrl(target, request));
  }

  if (role === 'CUSTOMER' && request.nextUrl.pathname.startsWith('/admin')) {
    return NextResponse.redirect(redirectUrl('/my-events', request));
  }

  return NextResponse.next();
}
