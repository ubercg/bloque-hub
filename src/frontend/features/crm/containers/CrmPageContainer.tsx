'use client';

import { useCallback, useMemo, useState } from 'react';
import useSWR from 'swr';
import {
  DndContext,
  DragEndEvent,
  DragOverlay,
  DragStartEvent,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import { toast } from 'sonner';

import { CAN_ACCESS_CRM, RoleGuard } from '@/features/auth';
import { formatDateOnlyLocal } from '@/lib/dateUtils';
import { useCrmLeads } from '../hooks/useCrmLeads';
import { useCrmQuotes } from '../hooks/useCrmQuotes';
import { useCrmSpaces } from '../hooks/useCrmSpaces';
import {
  createLead,
  createQuote,
  downloadContractSignedPdfBlob,
  downloadQuotePdfBlob,
  fetchQuoteContract,
  patchQuoteStatus,
  sendContractForSignature,
} from '../lib/crm.service';
import type { Contract, Lead, Quote, QuoteStatus } from '../types';

const COLUMNS: { id: QuoteStatus; title: string }[] = [
  { id: 'DRAFT', title: 'Borrador' },
  { id: 'DRAFT_PENDING_OPS', title: 'Pendiente Ops' },
  { id: 'SENT', title: 'Propuesta enviada' },
  { id: 'APPROVED', title: 'Aprobado' },
  { id: 'DIGITAL_APPROVED', title: 'Aprobado digital' },
];

const ALLOWED_TRANSITIONS: Record<QuoteStatus, QuoteStatus[]> = {
  DRAFT: ['DRAFT_PENDING_OPS', 'SENT'],
  DRAFT_PENDING_OPS: ['SENT'],
  SENT: ['APPROVED', 'DIGITAL_APPROVED'],
  APPROVED: [],
  DIGITAL_APPROVED: [],
};

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function DraggableCard({
  quote,
  lead,
  onClick,
}: {
  quote: Quote;
  lead?: Lead;
  onClick: (q: Quote) => void;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: quote.id });
  return (
    <button
      type="button"
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      className={`bg-white p-3 rounded border border-gray-200 shadow-sm text-left w-full cursor-grab active:cursor-grabbing ${isDragging ? 'opacity-50' : ''}`}
      onClick={() => onClick(quote)}
    >
      <p className="font-medium text-sm text-gray-900 truncate">{lead?.name ?? 'Sin lead'}</p>
      <p className="text-xs text-gray-500 truncate">{lead?.email ?? 'Sin email'}</p>
      <p className="text-xs text-gray-600 mt-1">Total: ${quote.total.toFixed(2)}</p>
      {quote.soft_hold_expires_at && (
        <p className="text-[11px] text-amber-700 mt-1">
          Hold: {new Date(quote.soft_hold_expires_at).toLocaleString('es-MX')}
        </p>
      )}
    </button>
  );
}

function DroppableColumn({
  id,
  title,
  quotes,
  leadsMap,
  onQuoteClick,
}: {
  id: QuoteStatus;
  title: string;
  quotes: Quote[];
  leadsMap: Map<string, Lead>;
  onQuoteClick: (q: Quote) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id });
  return (
    <div
      ref={setNodeRef}
      className={`bg-gray-100 rounded-lg p-3 w-72 shrink-0 flex flex-col min-h-[260px] ${isOver ? 'ring-2 ring-blue-400' : ''}`}
    >
      <h3 className="font-semibold text-gray-800 mb-2">
        {title} <span className="text-xs text-gray-500">({quotes.length})</span>
      </h3>
      <div className="space-y-2 flex-1">
        {quotes.map((q) => (
          <DraggableCard key={q.id} quote={q} lead={leadsMap.get(q.lead_id)} onClick={onQuoteClick} />
        ))}
      </div>
    </div>
  );
}

function ContractActions({
  quote,
  contract,
  onMutateQuotes,
}: {
  quote: Quote;
  contract: Contract | null | undefined;
  onMutateQuotes: () => void;
}) {
  const [sending, setSending] = useState(false);
  const [downloadingSigned, setDownloadingSigned] = useState(false);

  const sendContract = async () => {
    setSending(true);
    try {
      await sendContractForSignature(quote.id);
      toast.success('Contrato enviado para firma');
      onMutateQuotes();
    } catch (err: unknown) {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : 'Error al enviar contrato';
      toast.error(String(detail));
    } finally {
      setSending(false);
    }
  };

  const downloadSigned = async () => {
    if (!contract) return;
    setDownloadingSigned(true);
    try {
      const blob = await downloadContractSignedPdfBlob(contract.id);
      downloadBlob(blob, `contrato-${contract.id}-firmado.pdf`);
    } catch (err: unknown) {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : 'Error al descargar contrato';
      toast.error(String(detail));
    } finally {
      setDownloadingSigned(false);
    }
  };

  return (
    <div className="pt-3 border-t space-y-2">
      <p className="text-xs text-gray-500">
        Contrato:{' '}
        <span className="font-medium text-gray-700">
          {contract ? contract.status.toUpperCase() : 'No creado'}
        </span>
      </p>
      {quote.status === 'APPROVED' && !contract && (
        <button
          type="button"
          disabled={sending}
          onClick={() => void sendContract()}
          className="px-3 py-2 rounded bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          {sending ? 'Enviando...' : 'Enviar contrato a firma'}
        </button>
      )}
      {contract?.status === 'signed' && (
        <button
          type="button"
          disabled={downloadingSigned}
          onClick={() => void downloadSigned()}
          className="px-3 py-2 rounded border border-gray-300 text-sm font-medium hover:bg-gray-50 disabled:opacity-50"
        >
          {downloadingSigned ? 'Descargando...' : 'Descargar contrato firmado'}
        </button>
      )}
    </div>
  );
}

function QuoteDetailDrawer({
  quote,
  lead,
  onClose,
  onMutateQuotes,
}: {
  quote: Quote;
  lead?: Lead;
  onClose: () => void;
  onMutateQuotes: () => void;
}) {
  const [downloading, setDownloading] = useState(false);
  const { data: contract, isLoading: contractLoading } = useSWR<Contract | null>(
    ['crm-contract', quote.id],
    () => fetchQuoteContract(quote.id)
  );

  const downloadQuote = async () => {
    setDownloading(true);
    try {
      const blob = await downloadQuotePdfBlob(quote.id);
      downloadBlob(blob, `cotizacion-${quote.id}.pdf`);
    } catch {
      toast.error('No se pudo descargar la cotización');
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="fixed right-0 top-0 bottom-0 w-full max-w-xl bg-white border-l border-gray-200 shadow-xl z-50 flex flex-col">
      <div className="p-4 border-b flex justify-between items-center">
        <div>
          <h3 className="font-semibold text-gray-900">Detalle de cotización</h3>
          <p className="text-xs text-gray-500 font-mono">{quote.id}</p>
        </div>
        <button type="button" onClick={onClose} className="text-gray-500 hover:text-gray-700">
          Cerrar
        </button>
      </div>
      <div className="p-4 overflow-y-auto space-y-4">
        <div className="rounded-lg border border-gray-200 p-3">
          <p className="text-sm font-medium text-gray-800">{lead?.name ?? 'Sin lead'}</p>
          <p className="text-sm text-gray-600">{lead?.email ?? 'Sin email'}</p>
          {lead?.company && <p className="text-xs text-gray-500">{lead.company}</p>}
        </div>

        <div className="rounded-lg border border-gray-200 p-3">
          <p className="text-sm font-medium text-gray-800 mb-2">Resumen</p>
          <p className="text-sm text-gray-600">
            Estado: <span className="font-medium">{quote.status}</span>
          </p>
          <p className="text-sm text-gray-600">Total: ${quote.total.toFixed(2)}</p>
          {quote.soft_hold_expires_at && (
            <p className="text-sm text-gray-600">
              Soft hold hasta: {new Date(quote.soft_hold_expires_at).toLocaleString('es-MX')}
            </p>
          )}
        </div>

        <div className="rounded-lg border border-gray-200 p-3">
          <p className="text-sm font-medium text-gray-800 mb-2">Timeline de estado</p>
          <div className="flex gap-2 flex-wrap text-xs">
            {['DRAFT', 'DRAFT_PENDING_OPS', 'SENT', 'APPROVED', 'DIGITAL_APPROVED'].map((step) => (
              <span
                key={step}
                className={`px-2 py-1 rounded ${quote.status === step ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-500'}`}
              >
                {step}
              </span>
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-gray-200 p-3">
          <p className="text-sm font-medium text-gray-800 mb-2">Items</p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500">
                  <th className="py-1">Fecha</th>
                  <th className="py-1">Horario</th>
                  <th className="py-1">Precio</th>
                </tr>
              </thead>
              <tbody>
                {quote.items.map((item) => (
                  <tr key={item.id} className="border-t border-gray-100">
                    <td className="py-1">{formatDateOnlyLocal(item.fecha)}</td>
                    <td className="py-1">
                      {String(item.hora_inicio).slice(0, 5)} - {String(item.hora_fin).slice(0, 5)}
                    </td>
                    <td className="py-1">${item.precio.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="space-y-2">
          <button
            type="button"
            disabled={downloading}
            onClick={() => void downloadQuote()}
            className="px-3 py-2 rounded border border-gray-300 text-sm font-medium hover:bg-gray-50 disabled:opacity-50"
          >
            {downloading ? 'Descargando...' : 'Descargar cotización PDF'}
          </button>
          {contractLoading ? (
            <p className="text-xs text-gray-500">Cargando contrato...</p>
          ) : (
            <ContractActions quote={quote} contract={contract} onMutateQuotes={onMutateQuotes} />
          )}
        </div>
      </div>
    </div>
  );
}

function NewLeadModal({
  onClose,
  onSuccess,
}: {
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [company, setCompany] = useState('');
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!name.trim() || !email.trim()) return;
    setLoading(true);
    try {
      await createLead({
        name: name.trim(),
        email: email.trim(),
        phone: phone.trim() || null,
        company: company.trim() || null,
        notes: notes.trim() || null,
      });
      toast.success('Lead creado');
      onSuccess();
    } catch (err: unknown) {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : 'Error al crear lead';
      toast.error(String(detail));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl max-w-md w-full">
        <div className="p-4 border-b flex justify-between items-center">
          <h2 className="text-lg font-bold">Nuevo lead</h2>
          <button type="button" onClick={onClose} className="text-gray-500 hover:text-gray-700">
            Cerrar
          </button>
        </div>
        <div className="p-4 space-y-3">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Nombre"
            className="w-full border border-gray-300 rounded px-3 py-2"
          />
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Email"
            className="w-full border border-gray-300 rounded px-3 py-2"
          />
          <input
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="Teléfono (opcional)"
            className="w-full border border-gray-300 rounded px-3 py-2"
          />
          <input
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            placeholder="Empresa (opcional)"
            className="w-full border border-gray-300 rounded px-3 py-2"
          />
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Notas (opcional)"
            className="w-full border border-gray-300 rounded px-3 py-2 min-h-20"
          />
        </div>
        <div className="p-4 border-t flex justify-end gap-2">
          <button type="button" onClick={onClose} className="px-4 py-2 rounded border border-gray-300">
            Cancelar
          </button>
          <button
            type="button"
            disabled={loading || !name.trim() || !email.trim()}
            onClick={() => void submit()}
            className="px-4 py-2 rounded bg-blue-600 text-white disabled:opacity-50"
          >
            {loading ? 'Guardando...' : 'Guardar'}
          </button>
        </div>
      </div>
    </div>
  );
}

function ProposalBuilderModal({
  leads,
  onClose,
  onSuccess,
  onCreateLead,
}: {
  leads: Lead[];
  onClose: () => void;
  onSuccess: () => void;
  onCreateLead: () => void;
}) {
  const [leadId, setLeadId] = useState('');
  const [items, setItems] = useState<
    { space_id: string; fecha: string; hora_inicio: string; hora_fin: string }[]
  >([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const { data: spaces = [] } = useCrmSpaces();

  const addItem = () => {
    setItems((prev) => [
      ...prev,
      {
        space_id: spaces[0]?.id ?? '',
        fecha: '',
        hora_inicio: '09:00',
        hora_fin: '10:00',
      },
    ]);
  };

  const updateItem = (index: number, field: string, value: string) => {
    setItems((prev) => {
      const next = [...prev];
      (next[index] as Record<string, string>)[field] = value;
      return next;
    });
  };

  const removeItem = (index: number) => setItems((prev) => prev.filter((_, i) => i !== index));

  const validate = () => {
    if (!leadId) return 'Selecciona un lead.';
    if (items.length === 0) return 'Agrega al menos un slot.';
    for (const [idx, item] of items.entries()) {
      if (!item.space_id || !item.fecha || !item.hora_inicio || !item.hora_fin) {
        return `Completa todos los campos del slot #${idx + 1}.`;
      }
      if (item.hora_fin <= item.hora_inicio) {
        return `El horario del slot #${idx + 1} es inválido (fin debe ser mayor a inicio).`;
      }
    }
    const keys = items.map((i) => `${i.space_id}-${i.fecha}-${i.hora_inicio}-${i.hora_fin}`);
    if (new Set(keys).size !== keys.length) return 'Hay slots duplicados en la propuesta.';
    return '';
  };

  const handleSubmit = async () => {
    const validationMsg = validate();
    if (validationMsg) {
      setError(validationMsg);
      return;
    }
    setError('');
    setLoading(true);
    try {
      const data = await createQuote({
        lead_id: leadId,
        items: items.map((i) => ({
          space_id: i.space_id,
          fecha: i.fecha,
          hora_inicio: i.hora_inicio,
          hora_fin: i.hora_fin,
          // Precio no capturado en UI: backend calcula por reglas y fallback.
          precio: 0,
          item_order: 0,
        })),
      });
      toast.success('Cotización creada');
      const blob = await downloadQuotePdfBlob(data.id);
      downloadBlob(blob, `cotizacion-${data.id}.pdf`);
      onSuccess();
    } catch (err: unknown) {
      const response =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string }; status?: number } }).response
          : undefined;
      const msg =
        response?.status === 409
          ? 'Uno o más espacios no están disponibles en las fechas/horarios elegidos.'
          : (response?.data?.detail ?? 'Error al crear la cotización');
      setError(String(msg));
      toast.error(String(msg));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="p-4 border-b flex justify-between items-center">
          <h2 className="text-lg font-bold">Nueva propuesta</h2>
          <button type="button" onClick={onClose} className="text-gray-500 hover:text-gray-700">
            Cerrar
          </button>
        </div>
        <div className="p-4 space-y-4">
          <div className="flex justify-between items-end gap-2">
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-700 mb-1">Lead</label>
              <select
                value={leadId}
                onChange={(e) => setLeadId(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2"
              >
                <option value="">Seleccionar lead</option>
                {leads.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name} — {l.email}
                  </option>
                ))}
              </select>
            </div>
            <button
              type="button"
              onClick={onCreateLead}
              className="px-3 py-2 rounded border border-gray-300 text-sm font-medium hover:bg-gray-50"
            >
              Nuevo lead
            </button>
          </div>

          <div className="rounded border border-blue-100 bg-blue-50 p-2 text-xs text-blue-700">
            El precio final se calcula automáticamente en backend con reglas de pricing.
          </div>

          <div>
            <div className="flex justify-between items-center mb-2">
              <label className="block text-sm font-medium text-gray-700">Slots del evento</label>
              <button type="button" onClick={addItem} className="text-sm text-blue-600 hover:underline">
                + Añadir slot
              </button>
            </div>
            {items.map((item, idx) => (
              <div key={`${idx}-${item.space_id}`} className="grid grid-cols-1 md:grid-cols-5 gap-2 mb-2 p-2 bg-gray-50 rounded">
                <select
                  value={item.space_id}
                  onChange={(e) => updateItem(idx, 'space_id', e.target.value)}
                  className="border rounded px-2 py-1 text-sm"
                >
                  {spaces.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
                <input
                  type="date"
                  value={item.fecha}
                  onChange={(e) => updateItem(idx, 'fecha', e.target.value)}
                  className="border rounded px-2 py-1 text-sm"
                />
                <input
                  type="time"
                  value={item.hora_inicio}
                  onChange={(e) => updateItem(idx, 'hora_inicio', e.target.value)}
                  className="border rounded px-2 py-1 text-sm"
                />
                <input
                  type="time"
                  value={item.hora_fin}
                  onChange={(e) => updateItem(idx, 'hora_fin', e.target.value)}
                  className="border rounded px-2 py-1 text-sm"
                />
                <button type="button" onClick={() => removeItem(idx)} className="text-red-600 text-sm">
                  Quitar
                </button>
              </div>
            ))}
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>
        <div className="p-4 border-t flex justify-end gap-2">
          <button type="button" onClick={onClose} className="px-4 py-2 rounded border border-gray-300">
            Cancelar
          </button>
          <button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={loading}
            className="px-4 py-2 rounded bg-blue-600 text-white disabled:opacity-50"
          >
            {loading ? 'Creando...' : 'Crear cotización y descargar PDF'}
          </button>
        </div>
      </div>
    </div>
  );
}

function CrmContent() {
  const [activeQuote, setActiveQuote] = useState<Quote | null>(null);
  const [proposalOpen, setProposalOpen] = useState(false);
  const [leadModalOpen, setLeadModalOpen] = useState(false);
  const [selectedQuote, setSelectedQuote] = useState<Quote | null>(null);

  const { data: leads = [], mutate: mutateLeads } = useCrmLeads();
  const { data: quotes = [], mutate: mutateQuotes } = useCrmQuotes();

  const leadsMap = useMemo(() => new Map(leads.map((l) => [l.id, l])), [leads]);
  const quotesByStatus = useCallback((status: QuoteStatus) => quotes.filter((q) => q.status === status), [quotes]);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));

  const handleDragStart = (e: DragStartEvent) => {
    const id = e.active.id as string;
    const q = quotes.find((x) => x.id === id);
    if (q) setActiveQuote(q);
  };

  const handleDragEnd = async (e: DragEndEvent) => {
    setActiveQuote(null);
    const quoteId = e.active.id as string;
    const overId = e.over?.id;
    if (!overId || typeof overId !== 'string') return;
    const targetStatus = COLUMNS.find((c) => c.id === overId)?.id;
    if (!targetStatus) return;
    const quote = quotes.find((q) => q.id === quoteId);
    if (!quote || quote.status === targetStatus) return;
    if (!ALLOWED_TRANSITIONS[quote.status].includes(targetStatus)) {
      toast.error(`Transición no permitida: ${quote.status} -> ${targetStatus}`);
      return;
    }
    try {
      await patchQuoteStatus(quoteId, targetStatus);
      toast.success('Estado actualizado');
      await mutateQuotes();
    } catch (err: unknown) {
      const msg =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : 'Error al actualizar';
      toast.error(String(msg));
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">CRM</h1>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setLeadModalOpen(true)}
            className="px-4 py-2 rounded-lg border border-gray-300 text-gray-700 font-medium hover:bg-gray-50"
          >
            Nuevo lead
          </button>
          <button
            type="button"
            onClick={() => setProposalOpen(true)}
            className="px-4 py-2 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700"
          >
            Nueva propuesta
          </button>
        </div>
      </div>

      <DndContext sensors={sensors} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
        <div className="flex gap-4 overflow-x-auto pb-4">
          {COLUMNS.map((col) => (
            <DroppableColumn
              key={col.id}
              id={col.id}
              title={col.title}
              quotes={quotesByStatus(col.id)}
              leadsMap={leadsMap}
              onQuoteClick={setSelectedQuote}
            />
          ))}
        </div>
        <DragOverlay>
          {activeQuote ? (
            <div className="bg-white p-3 rounded border border-gray-200 shadow-lg opacity-95">
              <p className="font-medium text-sm text-gray-900">
                {leadsMap.get(activeQuote.lead_id)?.name ?? 'Sin lead'}
              </p>
              <p className="text-xs text-gray-500">{leadsMap.get(activeQuote.lead_id)?.email}</p>
              <p className="text-xs text-gray-600 mt-1">Total: ${activeQuote.total.toFixed(2)}</p>
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>

      {proposalOpen && (
        <ProposalBuilderModal
          leads={leads}
          onClose={() => setProposalOpen(false)}
          onCreateLead={() => {
            setProposalOpen(false);
            setLeadModalOpen(true);
          }}
          onSuccess={async () => {
            setProposalOpen(false);
            await mutateQuotes();
          }}
        />
      )}

      {leadModalOpen && (
        <NewLeadModal
          onClose={() => setLeadModalOpen(false)}
          onSuccess={async () => {
            setLeadModalOpen(false);
            await mutateLeads();
          }}
        />
      )}

      {selectedQuote && (
        <QuoteDetailDrawer
          quote={selectedQuote}
          lead={leadsMap.get(selectedQuote.lead_id)}
          onMutateQuotes={() => void mutateQuotes()}
          onClose={() => setSelectedQuote(null)}
        />
      )}
    </div>
  );
}

export function CrmPageContainer() {
  return (
    <RoleGuard allowedRoles={CAN_ACCESS_CRM}>
      <CrmContent />
    </RoleGuard>
  );
}
