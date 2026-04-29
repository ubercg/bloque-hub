import React, { useState, useEffect } from 'react';

export default function MetricsDashboard() {
  const [metrics, setMetrics] = useState({ kr23: 100, kr24: 100, kr25: 100, kr26: 100, kr27: 100 });

  return (
    <div className="metrics-dashboard">
      <h2>O-03, O-04, O-05 KPIs (Roadmap Fases 1-4)</h2>
      <div className="grid">
        <div className="card">KR-23 Justificación Descuentos: {metrics.kr23}%</div>
        <div className="card">KR-24 Invariancia Total MXN: {metrics.kr24}%</div>
        <div className="card">KR-25 Exactitud Pricing: {metrics.kr25}%</div>
        <div className="card">KR-26 Prevención Traslapes Montaje: {metrics.kr26}%</div>
        <div className="card">KR-27 Gating READY x Checklist: {metrics.kr27}%</div>
      </div>
    </div>
  );
}
