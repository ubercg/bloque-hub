'use client';

/**
 * Home Page - Landing institucional BLOQUE Hub
 * Propuesta de valor, acceso a catálogo y Mis eventos (si autenticado)
 */

import { useAuthStore } from '@/features/auth';
import { HeroSection } from '@/components/home/HeroSection';
import { ValueSection } from '@/components/home/ValueSection';
import { HowItWorksSection } from '@/components/home/HowItWorksSection';
import { CTASection } from '@/components/home/CTASection';
import CustomerHeader from '@/components/customer/CustomerHeader';

export default function Home() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  return (
    <>
      <CustomerHeader />
      <main id="main-content" className="min-h-screen bg-gray-50" role="main" tabIndex={-1}>
        <HeroSection showMyEvents={isAuthenticated} />
        <ValueSection />
        <HowItWorksSection />
        <CTASection />
      </main>
    </>
  );
}
