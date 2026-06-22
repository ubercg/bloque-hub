/**
 * Shared storageState file paths for authenticated E2E sessions.
 * Kept in a plain (non-test) module so both auth.setup.ts and spec files can
 * import them without Playwright's "test file importing test file" error.
 */
export const ADMIN_STATE = 'playwright/.auth/admin.json';
export const COMMERCIAL_STATE = 'playwright/.auth/commercial.json';
