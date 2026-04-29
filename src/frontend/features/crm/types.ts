export type QuoteStatus =
  | 'DRAFT'
  | 'DRAFT_PENDING_OPS'
  | 'SENT'
  | 'APPROVED'
  | 'DIGITAL_APPROVED';

export type ContractStatus = 'pending' | 'sent' | 'signed' | 'rejected' | 'expired';

export interface Lead {
  id: string;
  tenant_id: string;
  name: string;
  email: string;
  phone: string | null;
  company: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface QuoteItem {
  id: string;
  quote_id: string;
  space_id: string;
  fecha: string;
  hora_inicio: string;
  hora_fin: string;
  precio: number;
  item_order: number;
}

export interface Quote {
  id: string;
  tenant_id: string;
  lead_id: string;
  status: QuoteStatus;
  total: number;
  soft_hold_expires_at: string | null;
  created_at: string;
  updated_at: string;
  items: QuoteItem[];
}

export interface Contract {
  id: string;
  tenant_id: string;
  quote_id: string;
  status: ContractStatus;
  provider_document_id: string | null;
  signed_document_url: string | null;
  fea_provider: string | null;
  sent_at: string | null;
  delegate_signer_activated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Space {
  id: string;
  name: string;
  slug: string;
  precio_por_hora: number;
  piso: number | null;
}
