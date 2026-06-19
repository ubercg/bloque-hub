# Proposal: identity-superadmin

## Intent

Habilitar la gestión centralizada de usuarios por parte de los administradores (SUPERADMIN) en un entorno multi-tenant, permitiendo crear, editar, mover entre tenants, desactivar y resetear contraseñas de usuarios bajo la misma interfaz. Esto cubre un gap operativo crítico sin romper el aislamiento RLS, extendiendo las capacidades existentes del rol SUPERADMIN.

## Scope

### In Scope
- Endpoint `POST /users` para crear usuarios con validación global de email.
- Endpoint `PATCH /users/{id}` para edición (nombre, rol, estado), movimiento de tenant y reseteo administrativo de contraseña.
- Endpoint `DELETE /users/{id}` para borrado lógico (soft-deactivate).
- UI administrativa en el Frontend bajo `AdminShell` y `RoleGuard(SUPERADMIN)`.
- Reutilización y extensión de esquemas de validación y hashing de contraseñas (`UserUpdate`, `get_password_hash`).

### Out of Scope
- Creación de nuevos roles de sistema o migraciones de Enum `UserRole`.
- Modificaciones en la generación de JWT o la sesión base.
- Borrado físico de usuarios en la base de datos (hard delete).
- Flujo de self-service password reset (el alcance es solo reseteo administrativo).

## Capabilities

### New Capabilities
- `superadmin-user-management`: Gestión centralizada de ciclo de vida de usuarios (creación, edición, borrado lógico, y reseteo de contraseña) con validación de unicidad de email global.
- `superadmin-tenant-transfer`: Capacidad de mover usuarios entre tenants operando cross-tenant con contexto RLS explícito.

### Modified Capabilities
- None

## Approach

- **Email global**: Se agregará una validación explícita de nivel de servicio al crear o modificar email, asegurando unicidad en toda la DB, para evitar colisiones en `authenticate_user`.
- **Movimiento de tenant**: Se implementará el cambio de `tenant_id` forzando un contexto de DB de súper usuario: `get_db_context(tenant_id=None, role='SUPERADMIN')`, asegurando que la operación no quede huérfana de RLS.
- **Reseteo de contraseña**: `UserUpdate` incluirá un campo opcional `password`. El servicio lo hasheará usando `get_password_hash` antes de persistir, sin exponer nunca el hash.
- **Autorización y Router**: Los nuevos endpoints se agregarán a `identity/router.py` usando `Depends(require_tenant)` + `Depends(require_superadmin)`.
- **UI Next.js**: Creación de vistas en `AdminShell` consumiendo los nuevos endpoints, con protección de rutas de rol `SUPERADMIN`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/backend/app/modules/identity/schemas.py` | Modified | Agregar `UserUpdate` con soporte para password opcional y validación. |
| `src/backend/app/modules/identity/services.py` | Modified | Lógica CRUD (crear, soft-delete, editar/mover tenant con get_db_context especial, validar email). |
| `src/backend/app/modules/identity/router.py` | Modified | Nuevos endpoints POST, PATCH, DELETE con dependencias de auth existentes. |
| `Frontend (Next.js)` | New | Pantallas de lista de usuarios, formulario de creación y edición, reseteo de password bajo AdminShell. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Colisión de email en login si falla la validación de unicidad en BD. | Medium | Validación explícita en `services.py` antes de cualquier `add()` o actualización de email. Unit tests estrictos sobre este caso. |
| Pérdida de visibilidad por actualización de `tenant_id` bajo RLS restringido. | High | Inyectar sesión de base de datos con `get_db_context(tenant_id=None, role='SUPERADMIN')` exclusivamente para la transacción de movimiento. |

## Rollback Plan

- Revertir el PR o git commit.
- Ocultar los links de la UI de administración detrás de un feature flag (si estuviera disponible) o remover temporalmente el sub-menú de AdminShell.
- Como los cambios en DB (soft deletes) no destruyen datos, no se requiere restaurar backups. Los usuarios inactivos o movidos incorrectamente se pueden restaurar vía query o por el mismo servicio reparado.

## Dependencies

- Depende de los modelos, routers y dependencias de autenticación actuales (`identity`, `require_superadmin`, `RLS setup`).

## Success Criteria

- [ ] Un usuario SUPERADMIN puede listar, crear y soft-eliminar otros usuarios desde la UI y API.
- [ ] La validación de email bloquea correos duplicados en diferentes tenants.
- [ ] Mover a un usuario de tenant refleja el cambio correctamente en BD sin romper las reglas de RLS.
- [ ] La contraseña se puede resetear por el administrador de forma segura sin exponer el hash.