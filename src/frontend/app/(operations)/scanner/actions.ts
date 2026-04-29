'use server';

import { cookies } from 'next/headers';

// Define the expected response structure from the backend
interface ValidateQRResponse {
  acceso: 'AUTORIZADO' | 'RECHAZADO';
  color: 'VERDE' | 'ROJO';
  motivo: string;
  nombre?: string;
  espacio?: string;
}

// This should ideally come from an environment variable or a centralized config
const BACKEND_API_URL = process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:8000';

export async function validateQrCode(qrToken: string): Promise<ValidateQRResponse> {
  const cookieStore = await cookies();
  const tenantId = cookieStore.get('tenant_id')?.value; // Get tenant_id from cookies
  const accessToken = cookieStore.get('access_token')?.value; // Get access_token from cookies

  if (!tenantId || !accessToken) {
    throw new Error("Missing auth");
}
return { allowed: false, reason: "Mock implementation" } as any;
}