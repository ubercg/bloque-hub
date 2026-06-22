# Specs for Superadmin User Management

## Requirement: Authorization Enforcement
The system MUST restrict all user management mutations and tenant transfers to users with the SUPERADMIN role.

##### Scenario: Non-SUPERADMIN attempts mutation
- GIVEN an authenticated user with a NON-SUPERADMIN role (e.g., COMMERCIAL)
- WHEN the user attempts to execute `POST /users`, `PATCH /users/{id}`, `DELETE /users/{id}` or a tenant transfer
- THEN the system MUST respond with a **403 Forbidden** status code and not mutate any data
- AND this MUST be verified using pytest, reusing the existing authentication and authorization test patterns

## Requirement: User Creation
The system MUST allow a SUPERADMIN to create new users, enforcing global email uniqueness across all tenants.

##### Scenario: Create user successfully (Happy path)
- GIVEN a valid payload with name, email, and role
- WHEN the SUPERADMIN creates the user
- THEN the user MUST be created in the target tenant

##### Scenario: Create user with duplicate email globally
- GIVEN an email that already exists in another tenant
- WHEN the SUPERADMIN attempts to create a new user with this email
- THEN the system MUST return a **409 Conflict** status code indicating a validation error for email uniqueness

## Requirement: User Edition
The system MUST allow a SUPERADMIN to update a user's name, role, email, and `is_active` status via PATCH. The system MUST revalidate global email uniqueness if the email is modified.

##### Scenario: Edit user name and role
- GIVEN an existing user
- WHEN the SUPERADMIN updates the name and role
- THEN the user's details MUST be updated successfully

##### Scenario: Edit user email to a duplicate global email
- GIVEN an email that already exists in another tenant
- WHEN the SUPERADMIN updates a user's email to this duplicate email
- THEN the system MUST return a **409 Conflict** status code and abort the update

##### Scenario: Reactivate a soft-deleted user
- GIVEN an existing user that has been deactivated (`is_active` = False)
- WHEN the SUPERADMIN updates the user by setting `is_active` to True via PATCH
- THEN the user MUST be reactivated and allowed to authenticate again

##### Scenario: Edit a non-existent user
- GIVEN an invalid or non-existent user ID
- WHEN the SUPERADMIN attempts to update the user
- THEN the system MUST return a **404 Not Found** status code

## Requirement: Password Reset
The system MUST allow a SUPERADMIN to administratively reset a user's password. The system MUST NOT expose the new password hash in the response.

##### Scenario: Reset password
- GIVEN an existing user
- WHEN the SUPERADMIN provides a new password via PATCH
- THEN the system MUST hash the password and update it
- AND the system MUST NOT expose the hash in the response payload

## Requirement: Soft Delete
The system MUST allow a SUPERADMIN to logically delete (soft deactivate) a user.

##### Scenario: Soft delete an active user
- GIVEN an active user who is not the last SUPERADMIN
- WHEN the SUPERADMIN deletes the user
- THEN the user MUST be marked as inactive and blocked from authenticating

##### Scenario: Delete a non-existent user
- GIVEN an invalid or non-existent user ID
- WHEN the SUPERADMIN attempts to delete the user
- THEN the system MUST return a **404 Not Found** status code

## Requirement: Lockout Protection
The system MUST prevent a SUPERADMIN from deactivating, deleting, or transferring the last active SUPERADMIN of a tenant, including themselves, leaving the tenant without an administrator.

##### Scenario: Attempt to deactivate the last SUPERADMIN
- GIVEN a tenant with only one active SUPERADMIN
- WHEN the SUPERADMIN attempts to deactivate or remove this user
- THEN the system MUST reject the request and return a **409 Conflict** status code to prevent tenant lockout

## Requirement: Frontend and Backend Test Tooling
The system MUST enforce specific test tooling to validate frontend and backend capabilities.

##### Scenario: Test environment execution
- GIVEN the test suite runs
- WHEN backend logic is verified
- THEN it MUST use pytest, reusing patterns from `test_tenants_crud.py` and `test_identity_services.py`
- AND WHEN frontend logic is verified
- THEN it MUST exclusively use Playwright E2E tests (no jest/vitest unit runners)
