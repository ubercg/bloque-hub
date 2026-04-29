import { Metadata } from 'next';
import { ScannerClient } from '@/features/operations';

export const metadata: Metadata = {
  title: 'Bloque Hub | Scanner de Acceso',
  description: 'Herramienta de escaneo de QR para control de acceso físico.',
};

export default function ScannerPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-bloque-background p-4">
      <h1 className="mb-6 text-3xl font-bold text-bloque-text-dark">
        Control de Acceso
      </h1>
      <ScannerClient />
    </div>
  );
}