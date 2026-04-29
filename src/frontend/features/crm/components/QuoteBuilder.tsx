'use client';

import React, { useState, useEffect } from 'react';

interface QuoteBuilderProps {
  spaceId: string;
  basePrice: number;
  setQuote: (q: unknown) => void;
}

export default function QuoteBuilder({ spaceId: _spaceId, basePrice, setQuote: _setQuote }: QuoteBuilderProps) {
  const [duration, setDuration] = useState('6h');
  const [discount, setDiscount] = useState(0);
  const [justification, setJustification] = useState('');
  const [requiresApproval, setRequiresApproval] = useState(false);

  useEffect(() => {
    if (discount > 10) setRequiresApproval(true);
    else setRequiresApproval(false);
  }, [discount]);

  return (
    <div className="quote-builder">
      <h2>Constructor de Cotización Híbrida (KR-25)</h2>
      <select value={duration} onChange={(e) => setDuration(e.target.value)}>
        <option value="6h">Bloque 6h</option>
        <option value="12h">Bloque 12h</option>
        <option value="extra">Horas Extra</option>
      </select>
      <input type="number" placeholder="Descuento %" value={discount} onChange={e => setDiscount(Number(e.target.value))} />
      {requiresApproval && (
        <div>
          <span className="text-warning">Requiere Aprobación (KR-23)</span>
          <textarea placeholder="Justificación requerida" value={justification} onChange={e => setJustification(e.target.value)} />
        </div>
      )}
      <div className="preview">Precio Base: ${basePrice}</div>
    </div>
  );
}
