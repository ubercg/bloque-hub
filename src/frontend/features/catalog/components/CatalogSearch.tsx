'use client';

import { Search } from 'lucide-react';

interface CatalogSearchProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  id?: string;
  'aria-label'?: string;
  className?: string;
}

export function CatalogSearch({
  value,
  onChange,
  placeholder = 'Buscar espacios por nombre o descripción...',
  id = 'catalog-search',
  'aria-label': ariaLabel = 'Buscar espacios',
  className = '',
}: CatalogSearchProps) {
  return (
    <div className={`relative ${className}`}>
      <Search
        className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400 pointer-events-none"
        aria-hidden
      />
      <input
        id={id}
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={ariaLabel}
        className="w-full min-h-[48px] pl-12 pr-4 py-3 sm:py-3.5 rounded-2xl border-2 border-white/95 bg-white text-[#0F172A] placeholder:text-[#64748b] placeholder:font-normal focus:outline-none focus:ring-2 focus:ring-[#2563eb] focus:ring-offset-2 focus:ring-offset-transparent focus:border-[#2563eb] transition-[box-shadow,border-color] duration-200 shadow-sm"
      />
    </div>
  );
}
