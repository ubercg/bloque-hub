/**
 * CRM HTTP — sin React; usado por hooks SWR y acciones.
 */

import apiClient from '@/lib/http/apiClient';

import type { Contract, Lead, Quote, Space, QuoteStatus } from '../types';

export async function fetchLeads(): Promise<Lead[]> {
  const { data } = await apiClient.get<Lead[]>('/leads');
  return data;
}

export async function fetchQuotes(): Promise<Quote[]> {
  const { data } = await apiClient.get<Quote[]>('/quotes');
  return data;
}

export async function fetchSpaces(): Promise<Space[]> {
  const { data } = await apiClient.get<Space[]>('/spaces');
  return data;
}

export async function patchQuoteStatus(quoteId: string, status: QuoteStatus): Promise<void> {
  await apiClient.patch(`/quotes/${quoteId}/status`, { status });
}

export async function createLead(payload: {
  name: string;
  email: string;
  phone?: string | null;
  company?: string | null;
  notes?: string | null;
}): Promise<Lead> {
  const { data } = await apiClient.post<Lead>('/leads', payload);
  return data;
}

export async function createQuote(payload: {
  lead_id: string;
  items: {
    space_id: string;
    fecha: string;
    hora_inicio: string;
    hora_fin: string;
    precio: number;
    item_order: number;
  }[];
}): Promise<Quote> {
  const { data } = await apiClient.post<Quote>('/quotes', payload);
  return data;
}

export async function downloadQuotePdfBlob(quoteId: string): Promise<Blob> {
  const { data } = await apiClient.get(`/quotes/${quoteId}/download`, {
    responseType: 'blob',
  });
  return data as Blob;
}

export async function fetchQuoteContract(quoteId: string): Promise<Contract | null> {
  try {
    const { data } = await apiClient.get<Contract>(`/quotes/${quoteId}/contract`);
    return data;
  } catch (err: unknown) {
    const statusCode =
      err && typeof err === 'object' && 'response' in err
        ? (err as { response?: { status?: number } }).response?.status
        : undefined;
    if (statusCode === 404) return null;
    throw err;
  }
}

export async function sendContractForSignature(quoteId: string): Promise<Contract> {
  const { data } = await apiClient.post<Contract>(`/quotes/${quoteId}/send-contract`);
  return data;
}

export async function downloadContractSignedPdfBlob(contractId: string): Promise<Blob> {
  const { data } = await apiClient.get(`/contracts/${contractId}/signed-pdf`, {
    responseType: 'blob',
  });
  return data as Blob;
}
