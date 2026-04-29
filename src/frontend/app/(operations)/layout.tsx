'use client';

/**
 * Operations layout: checklists PWA and scanner.
 * Protected by middleware (auth required).
 * Registers manifest and service worker for offline support.
 */

import { useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ClipboardList, QrCode } from 'lucide-react';

export default function OperationsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  useEffect(() => {
    const link = document.createElement('link');
    link.rel = 'manifest';
    link.href = '/manifest-operations.json';
    document.head.appendChild(link);
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw-operations.js').catch(() => {});
    }
    return () => {
      link.remove();
    };
  }, []);

  return (
    <div className="min-h-screen bg-gray-100">
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center justify-between">
          <Link href="/operations/checklists" className="font-bold text-gray-900">
            BLOQUE Operaciones
          </Link>
          <nav className="flex gap-4">
            <Link
              href="/operations/checklists"
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium ${
                pathname?.startsWith('/operations/checklists')
                  ? 'bg-blue-100 text-blue-800'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              <ClipboardList className="w-4 h-4" />
              Checklists
            </Link>
            <Link
              href="/operations/scanner"
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium ${
                pathname === '/operations/scanner'
                  ? 'bg-blue-100 text-blue-800'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              <QrCode className="w-4 h-4" />
              Scanner
            </Link>
          </nav>
        </div>
      </header>
      <main className="max-w-4xl mx-auto px-4 py-6">{children}</main>
    </div>
  );
}
