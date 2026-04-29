# Features (dominio) — v3

- Importar desde `app/` solo la **API pública**: `@/features/<nombre>` (`index.ts` con exports explícitos; sin `export *`).
- **Containers** (`features/<name>/containers/`): composición SWR + store + UI; las `page.tsx` deben permanecer delgadas.
- **Hooks** (`hooks/`): datos con SWR; **services** (`lib/*.service.ts`): HTTP sin React; **store**: Zustand sin fetch.
- **Infra HTTP** global: `@/lib/http/apiClient`.
- **Middleware** importa `@/features/auth/server/*` (p. ej. `validateRequest` → `AuthContext`).
- **Layouts** en `app/`: composición y providers; sin fetch ni reglas de negocio (usar containers).

Módulos: `auth`, `booking`, `catalog`, `crm`, `operations`, `evidence`, `admin`.
