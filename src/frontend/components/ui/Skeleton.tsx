'use client';

/**
 * Skeleton loaders para estados de carga (UI Kit)
 * Variantes: card, list, text, table
 */

interface SkeletonProps {
  className?: string;
}

function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      className={`animate-pulse rounded-md bg-gray-200 ${className ?? ''}`.trim()}
      aria-hidden
    />
  );
}

/** Skeleton para una card de espacio (WeWork-style: imagen grande + título + capacidad/precio + CTA) */
export function SkeletonCard() {
  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden shadow-sm">
      <Skeleton className="h-64 w-full rounded-none" />
      <div className="p-4 space-y-3">
        <Skeleton className="h-5 w-3/4" />
        <div className="flex gap-4">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-4 w-28" />
        </div>
        <Skeleton className="h-4 w-24 mt-2" />
      </div>
    </div>
  );
}

/** Grid de skeleton cards (catálogo) */
export function SkeletonCardGrid({ count = 6 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}

/** Skeleton para una línea de lista */
export function SkeletonListRow() {
  return (
    <div className="flex items-center gap-4 py-3 border-b border-gray-100">
      <Skeleton className="h-10 w-10 rounded" />
      <div className="flex-1 space-y-2">
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-3 w-1/4" />
      </div>
      <Skeleton className="h-8 w-20 rounded" />
    </div>
  );
}

/** Bloque de texto (títulos + párrafos) */
export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-2">
      <Skeleton className="h-5 w-2/3" />
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className="h-4 w-full" />
      ))}
    </div>
  );
}

export { Skeleton };
export default Skeleton;
