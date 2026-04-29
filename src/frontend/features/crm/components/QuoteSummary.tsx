import React from 'react';

interface QuoteSummaryProps {
  subtotal: number;
  discounts: number;
  services: number;
}

export default function QuoteSummary({ subtotal, discounts, services }: QuoteSummaryProps) {
  const total = subtotal - discounts + services;
  return (
    <div className="quote-summary">
      <h3>Resumen Total (KR-24)</h3>
      <div>Subtotal Frozen: ${subtotal}</div>
      <div>Descuentos: -${discounts}</div>
      <div>Servicios: +${services}</div>
      <strong>Total Inmutable: ${total}</strong>
    </div>
  );
}
