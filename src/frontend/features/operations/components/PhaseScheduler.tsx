'use client';

import React, { useState } from 'react';

export default function PhaseScheduler() {
  const [phase, setPhase] = useState('USO');

  return (
    <div className="phase-scheduler">
      <h3>Agenda Discontinua y Fases (KR-26)</h3>
      <div className="tabs">
        <button onClick={() => setPhase('MONTAJE')} className={phase === 'MONTAJE' ? 'active' : ''}>MONTAJE</button>
        <button onClick={() => setPhase('USO')} className={phase === 'USO' ? 'active' : ''}>USO</button>
        <button onClick={() => setPhase('DESMONTAJE')} className={phase === 'DESMONTAJE' ? 'active' : ''}>DESMONTAJE</button>
      </div>
      {phase === 'MONTAJE' && <div className="text-warning">Sin Traslape Permitido</div>}
    </div>
  );
}
