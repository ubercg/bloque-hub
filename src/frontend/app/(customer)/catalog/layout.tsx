'use client';

/**
 * Catálogo — layout con tipografía marketplace (Poppins + Open Sans) y fondo cálido.
 * Design system: marketplace directory + vibrant block accents (ui-ux-pro-max).
 */

import { Suspense } from 'react';
import { Poppins, Open_Sans } from 'next/font/google';
import CustomerHeader from '@/components/customer/CustomerHeader';
import { EventCart } from '@/features/booking';
import { useAuthStore } from '@/features/auth';

const catalogDisplay = Poppins({
  subsets: ['latin'],
  weight: ['500', '600', '700'],
  variable: '--font-catalog-display',
  display: 'swap',
});

const catalogBody = Open_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-catalog-body',
  display: 'swap',
});

function CatalogLayoutContent({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  return (
    <div
      className={`${catalogDisplay.variable} ${catalogBody.variable} catalog-shell min-h-screen flex flex-col bg-white text-[#0f172a] antialiased`}
    >
      <CustomerHeader />
      <div className="flex-1">{children}</div>
      {isAuthenticated && <EventCart />}
    </div>
  );
}

export default function CatalogLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense
      fallback={
        <div
          className={`${catalogDisplay.variable} ${catalogBody.variable} catalog-shell flex min-h-screen items-center justify-center bg-white`}
        >
          <div className="font-catalog-display text-lg font-semibold text-[#78350F]">Cargando catálogo…</div>
        </div>
      }
    >
      <CatalogLayoutContent>{children}</CatalogLayoutContent>
    </Suspense>
  );
}
