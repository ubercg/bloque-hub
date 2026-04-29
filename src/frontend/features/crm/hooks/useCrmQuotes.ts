'use client';

import useSWR from 'swr';

import { fetchQuotes } from '../lib/crm.service';
import type { Quote } from '../types';

export function useCrmQuotes() {
  return useSWR<Quote[]>('/quotes', fetchQuotes);
}
