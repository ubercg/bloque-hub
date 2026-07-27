'use client';

/**
 * Document upload block, adapted from `booking/confirm/page.tsx` (RN-015,
 * design §6.5) — same drag/drop `<label>` + hidden file `<input>` and same
 * MIME/size messaging as the existing KYC upload flow (no rule change).
 * The wizard has no per-type document catalog, so this collects a flat
 * list of files into a single `store.documents` bucket.
 */

import { useState } from 'react';
import { FileUp } from 'lucide-react';

import {
  DOCUMENT_ACCEPT,
  DOCUMENT_INVALID_TYPE_MESSAGE,
  DOCUMENT_MAX_SIZE_BYTES,
  DOCUMENT_SIZE_MESSAGE,
  DOCUMENT_TOO_LARGE_MESSAGE,
} from '../constants';
import { useQuoteWizardStore } from '../store/quote-wizard.store';

const DOCUMENTS_BUCKET_KEY = 'adjuntos';

const ALLOWED_MIME = new Set(['application/pdf', 'image/jpeg', 'image/jpg', 'image/png']);

function isAllowedFile(file: File): boolean {
  if (ALLOWED_MIME.has(file.type)) return true;
  // Some browsers/drag-drop sources omit `type`; fall back to extension.
  return /\.(pdf|jpe?g|png)$/i.test(file.name);
}

export function DocumentUpload() {
  const documents = useQuoteWizardStore((s) => s.documents);
  const setField = useQuoteWizardStore((s) => s.setField);

  const files = Array.isArray(documents[DOCUMENTS_BUCKET_KEY])
    ? (documents[DOCUMENTS_BUCKET_KEY] as File[])
    : [];

  const addFile = (file: File): string | null => {
    if (!isAllowedFile(file)) return DOCUMENT_INVALID_TYPE_MESSAGE;
    if (file.size > DOCUMENT_MAX_SIZE_BYTES) return DOCUMENT_TOO_LARGE_MESSAGE;
    setField('documents', { ...documents, [DOCUMENTS_BUCKET_KEY]: [...files, file] });
    return null;
  };

  const removeFile = (index: number) => {
    const next = [...files];
    next.splice(index, 1);
    setField('documents', { ...documents, [DOCUMENTS_BUCKET_KEY]: next });
  };

  const [error, setErrorState] = useState<string | null>(null);

  return (
    <div>
      <label htmlFor="documentos" className="block text-sm font-medium text-gray-700 mb-1">
        Documentos (opcional)
      </label>
      <p className="text-xs text-gray-500 mb-2">{DOCUMENT_SIZE_MESSAGE}</p>

      <label
        htmlFor="documentos"
        onDragOver={(e) => {
          e.preventDefault();
          e.stopPropagation();
        }}
        onDrop={(e) => {
          e.preventDefault();
          const f = e.dataTransfer.files[0];
          if (f) {
            const err = addFile(f);
            setErrorState(err);
          }
        }}
        className="flex flex-col items-center justify-center gap-2 border-2 border-dashed border-gray-200 rounded-lg px-4 py-6 cursor-pointer hover:border-blue-400 hover:bg-blue-50/40 transition"
      >
        <FileUp className="w-7 h-7 text-gray-400" />
        <span className="text-sm text-gray-700 text-center">Arrastra o haz clic para elegir archivo</span>
        <input
          id="documentos"
          type="file"
          accept={DOCUMENT_ACCEPT}
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) {
              const err = addFile(f);
              setErrorState(err);
            }
            e.target.value = '';
          }}
        />
      </label>

      {error && (
        <p role="alert" className="text-sm text-red-600 mt-2">
          {error}
        </p>
      )}

      {files.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm text-gray-700">
          {files.map((f, i) => (
            <li key={`${f.name}-${i}`} className="flex items-center justify-between gap-2">
              <span className="truncate">{f.name}</span>
              <button
                type="button"
                className="text-red-600 text-xs shrink-0"
                onClick={() => removeFile(i)}
              >
                Quitar
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
