'use client';

import useSWR from 'swr';

import { fetchSpaces } from '../lib/crm.service';
import type { Space } from '../types';

export function useCrmSpaces() {
  return useSWR<Space[]>('/spaces', fetchSpaces);
}
