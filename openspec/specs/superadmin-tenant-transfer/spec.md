# Specs for Superadmin Tenant Transfer

## Requirement: Tenant Transfer
The system MUST allow a SUPERADMIN to move a user from one tenant to another, executing cross-tenant operations using an explicit DB context that safely overrides default RLS restrictions. This logic MUST be validated via integration testing.

##### Scenario: Move user to another tenant (Integration RLS validation)
- GIVEN an active user in Tenant A and a destination Tenant B
- WHEN the SUPERADMIN updates the user's tenant_id to Tenant B
- THEN the system MUST successfully transfer the user using an elevated DB context
- AND this operation MUST be verified by an integration test against a real Postgres database with RLS active (reusing patterns from `test_inventory_superadmin_tenant.py` and `test_rls_isolation.py`)
- AND the system MUST NOT rely on mocked unit tests to validate this RLS logic
