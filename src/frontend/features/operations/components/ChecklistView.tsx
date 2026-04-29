'use client';

import React, { useState } from 'react';

interface ChecklistItem {
  id: string;
  description: string;
  is_critical?: boolean;
}

interface ChecklistViewProps {
  items: ChecklistItem[];
  onComplete?: () => void;
}

export default function ChecklistView({ items, onComplete: _onComplete }: ChecklistViewProps) {
  const [completedItems, setCompletedItems] = useState<string[]>([]);

  const allCriticalCompleted = items
    .filter((i) => i.is_critical)
    .every((i) => completedItems.includes(i.id));

  return (
    <div className="checklist-view">
      <h3>Checklist de Montaje (KR-27)</h3>
      {items.map(item => (
        <div key={item.id}>
          <input 
            type="checkbox" 
            checked={completedItems.includes(item.id)} 
            onChange={(e) => {
              if (e.target.checked) setCompletedItems([...completedItems, item.id]);
              else setCompletedItems(completedItems.filter(id => id !== item.id));
            }} 
          />
          {item.description} {item.is_critical && <span className="critical">⚠️ Crítico</span>}
        </div>
      ))}
      {!allCriticalCompleted && <div className="gating-blocked">GATING: Bloqueado a READY</div>}
      {allCriticalCompleted && <div className="gating-passed">GATING: READY Permitido</div>}
    </div>
  );
}
