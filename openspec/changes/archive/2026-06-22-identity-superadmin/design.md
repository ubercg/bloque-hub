# Design: identity-superadmin

## Technical Approach

We will extend the `identity` module to support centralized user management by `SUPERADMIN`s. We will add `POST /users`, `PATCH /users/{id}`, and `DELETE /users/{id}` endpoints. To bypass Postgres RLS safely and atomically during tenant transfers and global email uniqueness checks, ALL operations inside `update_user` (email-check, move-tenant, and standard property updates) will run in a single transaction under an elevated DB context (`get_db_context(tenant_id=None, role="SUPERADMIN")`). The frontend will implement new Next.js views using the `(admin)` route group, utilizing the existing `admin/403/page.tsx` guard.

## Architecture Decisions

### Decision: Atomic Cross-Tenant Updates
**Choice**: Run the entire `update_user` workflow (email validation, tenant transfer, and field updates) in a single transaction using `get_db_context(tenant_id=None, role="SUPERADMIN")`.
**Alternatives considered**: Split sessions where email check/tenant updates use elevated context and normal updates use a standard session.
**Rationale**: Split sessions risk partial updates and race conditions. A single transaction under elevated context guarantees atomicity, ensuring full consistency across standard properties, tenant movement, and email checks without RLS interference.

### Decision: Elevated Lockout Protection
**Choice**: The lockout check (verifying active SUPERADMIN count) must run under an elevated context on the affected user's tenant before deactivation/deletion/transfer.
**Alternatives considered**: Running the check under the executing user's session context.
**Rationale**: If a SUPERADMIN transfers another SUPERADMIN from tenant A to B, the count check must query tenant A (the source). Elevated context ensures this cross-tenant check does not fail due to RLS blocks.

## Data Flow

    [Frontend (admin) Route Group]
         │
         ▼ (POST / PATCH / DELETE)
    [FastAPI Router (identity/router.py)]
         │ (Requires SUPERADMIN)
         ▼
    [Identity Service (services.py)]
         │
         ▼ [Single Elevated DB Transaction (get_db_context(tenant_id=None, role="SUPERADMIN"))]
         ├──> Validate Lockout (on affected user's tenant)
         ├──> Validate Global Email Uniqueness
         └──> Update user fields (name, role, password, tenant_id, is_active)

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/backend/app/modules/identity/schemas.py` | Modify | Add `UserUpdate` with optional `password`, `tenant_id`, `email`, etc. |
| `src/backend/app/modules/identity/services.py` | Modify | Add CRUD functions: `create_user`, `update_user`, `delete_user`. `update_user` runs fully in one elevated transaction. |
| `src/backend/app/modules/identity/router.py` | Modify | Add `POST /users`, `PATCH /users/{id}`, `DELETE /users/{id}` with `require_superadmin`. |
| `src/frontend/app/(admin)/admin/users/page.tsx` | Create | New user list dashboard for SUPERADMINs under the `(admin)` route group. |
| `src/frontend/app/(admin)/admin/users/[id]/page.tsx` | Create | Edit/transfer form UI for SUPERADMINs. |
| `src/frontend/features/admin/...` | Create | Components for the admin user management (following crm/spaces pattern). |

## Interfaces / Contracts

```python
class UserUpdate(BaseModel):
    tenant_id: UUID | None = None
    email: EmailStr | None = None
    full_name: str | None = Field(None, min_length=1, max_length=255)
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(None, min_length=8)
```

**New Endpoints:**
- `POST /api/users`: Consumes `UserCreate`. Returns `UserRead`.
- `PATCH /api/users/{user_id}`: Consumes `UserUpdate`. Returns `UserRead`.
- `DELETE /api/users/{user_id}`: Soft delete, sets `is_active=False`.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Integration | Global email uniqueness validation | Real Postgres DB testing (no unit mocks). Mocking gives false confidence for RLS contexts. |
| Integration | Cross-tenant move & RLS | Real Postgres DB testing that an elevated context successfully updates `tenant_id` atomically despite RLS. |
| Integration | Lockout prevention | Assert 409 Conflict when deleting/moving the last active SUPERADMIN using real Postgres. |
| E2E | Admin UI user flow | Playwright tests navigating `(admin)` routes to create, edit, and move a user. |

## Migration / Rollout

No migration required. The `UserRole` and DB schema are not changing. Rollout consists of merging the feature, and it will be instantly available to users with `SUPERADMIN` role via the `(admin)` routes.

## Open Questions

- None