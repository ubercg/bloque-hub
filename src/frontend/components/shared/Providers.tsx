'use client';

/**
 * Global providers: Toaster and cross-feature shells only.
 */

import { ReactNode } from 'react';
import { Toaster } from 'sonner';

interface ProvidersProps {
  children: ReactNode;
}

export function Providers({ children }: ProvidersProps) {
  return (
    <>
      {children}
      <Toaster richColors position="top-center" closeButton />
    </>
  );
}
