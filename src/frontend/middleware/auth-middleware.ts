import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

import { isStaffRole } from '@/features/auth/server/session';
import { validateAuthFromNextRequest } from '@/features/auth/server/validateRequest';

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
        const loginUrl = new URL('/login', request.url);
        loginUrl.searchParams.set('redirect', request.nextUrl.pathname);
        return NextResponse.redirect(loginUrl);
      }
      return NextResponse.next();
    }
    const response = NextResponse.redirect(new URL('/login', request.url));
    response.cookies.delete('auth_token');
    return response;
  }

  const role = ctx.role;
  const staff = isStaffRole(role);

  if (isAuthPage) {
    const target = staff ? '/admin/dashboard' : '/my-events';
    return NextResponse.redirect(new URL(target, request.url));
  }

  if (role === 'CUSTOMER' && request.nextUrl.pathname.startsWith('/admin')) {
    return NextResponse.redirect(new URL('/my-events', request.url));
  }

  return NextResponse.next();
}
