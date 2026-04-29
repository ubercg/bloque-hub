# UI Kit — Componentes reutilizables

Componentes base del sistema de diseño para BLOQUE Hub. Se usan en catálogo, portal y (cuando exista) back-office (Tarea 15).

## Componentes

### Skeleton

Estados de carga consistentes.

- **Skeleton** – Bloque base animado (`animate-pulse`).
- **SkeletonCard** / **SkeletonCardGrid** – Cards y grid para catálogo.
- **SkeletonListRow** – Filas de lista (portal, evidencias).
- **SkeletonText** – Párrafos y títulos.

### DataTable

Tabla de datos para listados y dashboards.

- **Props**: `columns`, `rows`, `isLoading`, `emptyMessage`, `ariaCaption`, `getRowKey`.
- **columns**: `{ key, label, render?, className?, hideOnMobile? }`.
- Soporta skeleton integrado y estado vacío. Accesible (caption, scope col).

Uso en back-office cuando existan vistas de CRM, Finanzas o Control Center.

### ChartContainer

Contenedor estándar para gráficos (KPIs, reservas por mes, etc.).

- **Props**: `title`, `description?`, `isLoading`, `children`, `minHeight?`.
- Incluye región ARIA, título y skeleton de carga. El contenido (Recharts, Chart.js u otro) se pasa como `children`.

Uso en dashboards de Tarea 15 cuando existan.

### Toast (Sonner)

Feedback visual para acciones CRUD. Configurado en [`components/shared/Providers.tsx`](../shared/Providers.tsx):

- `toast.success()`, `toast.error()`, `toast.info()` desde cualquier componente.

## Dependencias

- **sonner**: toasts (ya en proyecto).
- Para gráficos futuros: añadir Recharts o Chart.js cuando se implementen dashboards.
