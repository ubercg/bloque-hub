'use client';

import React, { useState } from 'react';

export default function AdditionalServicesSelector() {
  const [services, setServices] = useState([{ name: 'Limpieza', unit: 'EVENTO', price: 1000 }]);
  
  return (
    <div className="additional-services">
      <h3>Servicios Modulares</h3>
      <ul>
        {services.map((s, i) => (
          <li key={i}>{s.name} - {s.unit}: ${s.price}</li>
        ))}
      </ul>
      <input type="number" placeholder="Cantidad" defaultValue={1} />
    </div>
  );
}
