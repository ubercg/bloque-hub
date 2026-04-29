'use client';

/**
 * ChartContainer - Contenedor estándar para gráficos del UI Kit
 * Para dashboards (EP-05 / Tarea 15). Incluye título, estado de carga y área para el gráfico.
 * Integrar con librería de charts (Recharts, Chart.js, etc.) cuando se use en back-office.
 *
 * @example
 * <ChartContainer title="Reservas por mes" isLoading={loading}>
 *   <RechartsBar data={data} />
 * </ChartContainer>
 */

import { Skeleton } from './Skeleton';

interface ChartContainerProps {
  title: string;
  /** Descripción opcional para accesibilidad */
  description?: string;
  isLoading?: boolean;
  children?: React.ReactNode;
  className?: string;
  /** Altura mínima del área del gráfico */
  minHeight?: number;
}

export function ChartContainer({
  title,
  description,
  isLoading = false,
  children,
  className,
  minHeight = 280,
}: ChartContainerProps) {
  return (
    <div
      className={`rounded-xl border border-gray-200 bg-white overflow-hidden ${className ?? ''}`}
      role="region"
      aria-labelledby="chart-title"
      aria-describedby={description ? 'chart-desc' : undefined}
    >
      <div className="px-4 sm:px-6 py-4 border-b border-gray-100">
        <h3 id="chart-title" className="text-base font-semibold text-gray-900">
          {title}
        </h3>
        {description && (
          <p id="chart-desc" className="text-sm text-gray-500 mt-0.5">
            {description}
          </p>
        )}
      </div>
      <div
        className="p-4 sm:p-6 flex items-center justify-center"
        style={{ minHeight }}
      >
        {isLoading ? (
          <div className="w-full space-y-3" aria-busy="true">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-[200px] w-full rounded-lg" />
            <div className="flex gap-4 justify-center">
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-3 w-16" />
            </div>
          </div>
        ) : (
          children ?? (
            <p className="text-gray-500 text-sm">Sin datos para mostrar</p>
          )
        )}
      </div>
    </div>
  );
}
