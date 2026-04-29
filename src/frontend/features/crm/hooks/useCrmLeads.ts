'use client';

import useSWR from 'swr';

import { fetchLeads } from '../lib/crm.service';
import type { Lead } from '../types';

export function useCrmLeads() {
  return useSWR<Lead[]>('/leads', fetchLeads);
}
