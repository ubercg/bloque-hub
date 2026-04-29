'use client';

/**
 * DataTable - Componente de tabla reutilizable del UI Kit
 * Para dashboards y vistas de back-office (EP-05 / Tarea 15).
 *
 * @example
 * <DataTable
 *   columns={[{ key: 'name', label: 'Nombre' }, { key: 'email', label: 'Email' }]}
 *   rows={data}
 *   isLoading={loading}
 *   emptyMessage="No hay registros"
 *   ariaCaption="Listado de usuarios"
 * />
 */

import { Skeleton } from './Skeleton';

export interface DataTableColumn<T> {
  key: keyof T | string;
  label: string;
  /** Render celda personalizado */
  render?: (row: T) => React.ReactNode;
  /** Clases para th/td */
  className?: string;
  /** Ocultar en móvil */
  hideOnMobile?: boolean;
}

interface DataTableProps<T extends Record<string, unknown>> {
  columns: DataTableColumn<T>[];
  rows: T[];
  isLoading?: boolean;
  emptyMessage?: string;
  /** Para accesibilidad (tabla con caption) */
  ariaCaption?: string;
  /** Key único por fila para React */
  getRowKey: (row: T) => string;
  className?: string;
}

export function DataTable<T extends Record<string, unknown>>({
  columns,
  rows,
  isLoading = false,
  emptyMessage = 'No hay datos',
  ariaCaption,
  getRowKey,
  className,
}: DataTableProps<T>) {
  const getCellValue = (row: T, col: DataTableColumn<T>): React.ReactNode => {
    if (col.render) return col.render(row);
    const val = row[col.key as keyof T];
    return val != null ? String(val) : '—';
  };

  if (isLoading) {
    return (
      <div className={`overflow-x-auto rounded-xl border border-gray-200 ${className ?? ''}`}>
        <table className="w-full min-w-[500px]" role="table" aria-busy="true">
          <thead>
            <tr>
              {columns.map((col) => (
                <th
                  key={String(col.key)}
                  className={`px-4 py-3 text-left text-sm font-semibold text-gray-700 bg-gray-50 border-b border-gray-200 ${col.hideOnMobile ? 'hidden sm:table-cell' : ''} ${col.className ?? ''}`}
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[1, 2, 3, 4, 5].map((i) => (
              <tr key={i} className="border-b border-gray-100 last:border-0">
                {columns.map((col) => (
                  <td
                    key={String(col.key)}
                    className={`px-4 py-3 ${col.hideOnMobile ? 'hidden sm:table-cell' : ''}`}
                  >
                    <Skeleton className="h-4 w-3/4" />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className={`overflow-x-auto rounded-xl border border-gray-200 bg-white ${className ?? ''}`}>
      <table className="w-full min-w-[500px]" role="table" aria-label={ariaCaption}>
        {ariaCaption && (
          <caption className="sr-only">{ariaCaption}</caption>
        )}
        <thead>
          <tr className="bg-gray-50">
            {columns.map((col) => (
              <th
                key={String(col.key)}
                scope="col"
                className={`px-4 py-3 text-left text-sm font-semibold text-gray-700 border-b border-gray-200 ${col.hideOnMobile ? 'hidden sm:table-cell' : ''} ${col.className ?? ''}`}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-4 py-12 text-center text-gray-500">
                {emptyMessage}
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr
                key={getRowKey(row)}
                className="border-b border-gray-100 last:border-0 hover:bg-gray-50/50 transition"
              >
                {columns.map((col) => (
                  <td
                    key={String(col.key)}
                    className={`px-4 py-3 text-sm text-gray-900 ${col.hideOnMobile ? 'hidden sm:table-cell' : ''} ${col.className ?? ''}`}
                  >
                    {getCellValue(row, col)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
