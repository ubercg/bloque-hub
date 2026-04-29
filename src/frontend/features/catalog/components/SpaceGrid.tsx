'use client';

interface SpaceGridProps {
  children: React.ReactNode;
  className?: string;
}

export function SpaceGrid({ children, className = '' }: SpaceGridProps) {
  return (
    <div
      className={`grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6 sm:gap-8 transition-opacity duration-300 ${className}`}
      role="list"
    >
      {children}
    </div>
  );
}
