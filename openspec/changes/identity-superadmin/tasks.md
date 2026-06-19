# Tasks: identity-superadmin

## Strategy
**Delivery strategy**: ask-always
**Chain strategy**: feature-branch-chain
**Review Workload Forecast**: 
- Estimated Lines Changed: 600
- 400-line budget risk: High
- Chained PRs recommended: Yes
- Decision needed before apply: Yes

## Task List

### Phase 1: Backend Implementation (Schemas & Services)
- [ ] 1. Update `src/backend/app/modules/identity/schemas.py`: Add `UserUpdate` schema with optional fields `tenant_id`, `email`, `full_name`, `role`, `is_active`, and `password`.
- [ ] 2. Update `src/backend/app/modules/identity/services.py`: Implement `create_user`. Ensure global email uniqueness check runs under elevated context `get_db_context(tenant_id=None, role="SUPERADMIN")`. Hash password using `get_password_hash`.
- [ ] 3. Update `src/backend/app/modules/identity/services.py`: Implement `update_user`. Must run entirely under ONE elevated transaction (`get_db_context(tenant_id=None, role="SUPERADMIN")`). Handle email uniqueness, lockout protection (don't disable/move last SUPERADMIN), and field updates atomically.
- [ ] 4. Update `src/backend/app/modules/identity/services.py`: Implement `delete_user` for soft-deletion (set `is_active=False`), reusing lockout protection.

### Phase 2: Backend Router & Auth Enforcement
- [ ] 5. Update `src/backend/app/modules/identity/router.py`: Add `POST /users`, `PATCH /users/{id}`, and `DELETE /users/{id}`. Protect all with `Depends(require_tenant)` and `Depends(require_superadmin)`.
- [ ] 6. Ensure error codes match spec: 404 (Not Found), 403 (Forbidden for non-SUPERADMIN), 409 (Conflict for email duplicate or lockout protection).

### Phase 3: Backend Integration Tests (Strict Pytest without DB Mocks)
- [ ] 7. Create integration tests for Auth Enforcement: Verify `COMMERCIAL` role gets `403 Forbidden` for POST/PATCH/DELETE endpoints.
- [ ] 8. Create integration tests for Global Email Check: Verify email collisions across different tenants are caught and return `409 Conflict`.
- [ ] 9. Create integration tests for Move Tenant (RLS): Verify `update_user` successfully moves a user between tenants and updates properties simultaneously without RLS issues.
- [ ] 10. Create integration tests for Lockout Protection: Verify attempting to deactivate or move the last active SUPERADMIN returns `409 Conflict`.

### Phase 4: Frontend Implementation (Admin UI)
- [ ] 11. Create components in `src/frontend/features/admin/users/`: User list, create form, and edit/transfer form components following the CRM/spaces pattern.
- [ ] 12. Create `src/frontend/app/(admin)/admin/users/page.tsx`: Route for the user list dashboard, guarded by `RoleGuard(SUPERADMIN)`.
- [ ] 13. Create `src/frontend/app/(admin)/admin/users/[id]/page.tsx`: Route for editing/transferring a specific user.

### Phase 5: Frontend E2E Tests (Playwright)
- [ ] 14. Create E2E tests in `src/frontend/tests/e2e/admin/users.spec.ts`: Test the happy paths for creating, editing, and transferring a user as a SUPERADMIN.
- [ ] 15. Create E2E tests for error states: Verify global duplicate email error UI handling and lockout protection error messages.

## Verification
- Backend tests pass locally: `pytest tests/`
- Frontend E2E tests pass locally: `npx playwright test`
- Manual review of atomic transaction code to ensure no context leaking or split sessions.