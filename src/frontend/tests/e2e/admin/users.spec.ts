import { test, expect } from '@playwright/test';

import { COMMERCIAL_STATE } from '../auth-paths';

const BASE_PATH = '/bloque';
const ADMIN_EMAIL = 'admin@test.com';

/**
 * Admin tests reuse the SUPERADMIN storageState configured on the project
 * (see playwright.config.ts), so no per-test UI login is needed.
 */
test.describe('Admin Users Management (Superadmin)', () => {
  test('should display a list of users and navigate to create', async ({ page }) => {
    await page.goto(`${BASE_PATH}/admin/users`);
    await expect(page.getByRole('heading', { name: 'Administración de Usuarios' })).toBeVisible({ timeout: 15000 });

    // Check if there's at least one user in the list (the admin themselves)
    await expect(page.getByRole('cell', { name: ADMIN_EMAIL })).toBeVisible({ timeout: 15000 });

    await page.getByRole('link', { name: 'Nuevo Usuario' }).click();
    await expect(page).toHaveURL((url) => url.pathname.includes('/admin/users/create'));
  });

  test('should allow creating a new user and deleting it', async ({ page }) => {
    await page.goto(`${BASE_PATH}/admin/users/create`);

    const newEmail = `e2e_test_${Date.now()}@test.com`;

    // Extract tenantId from localStorage where zustand auth store is saved
    const authStorageStr = await page.evaluate(() => localStorage.getItem('auth-storage'));
    const tenantId = authStorageStr ? JSON.parse(authStorageStr).state.tenantId : '';

    await page.getByLabel('ID del Tenant').fill(tenantId);
    await page.getByLabel('Nombre Completo').fill('E2E Test User');
    await page.getByLabel('Email', { exact: true }).fill(newEmail);
    await page.getByLabel('Contraseña', { exact: true }).fill('password123');
    await page.locator('select#role').selectOption('CUSTOMER');

    await page.getByRole('button', { name: 'Crear Usuario' }).click();

    // Verify it navigates back and the user is created. Generous timeouts absorb
    // dev-mode (Turbopack) recompile latency after each mutation/navigation.
    await expect(page).toHaveURL((url) => url.pathname.endsWith('/admin/users'), { timeout: 15000 });
    await expect(page.getByRole('cell', { name: newEmail })).toBeVisible({ timeout: 15000 });

    // Now edit and deactivate it
    await page.getByRole('row', { name: newEmail }).getByRole('link', { name: 'Editar' }).click();
    await expect(page.getByRole('heading', { name: 'Editar Usuario: E2E Test User' })).toBeVisible({ timeout: 15000 });

    await page.getByRole('button', { name: 'Desactivar Usuario' }).click();
    await expect(page).toHaveURL((url) => url.pathname.endsWith('/admin/users'), { timeout: 15000 });
    await expect(page.getByRole('row', { name: newEmail }).getByText('Inactivo')).toBeVisible({ timeout: 15000 });

    // Reactivate
    await page.getByRole('row', { name: newEmail }).getByRole('link', { name: 'Editar' }).click();
    await expect(page.getByRole('heading', { name: 'Editar Usuario: E2E Test User' })).toBeVisible({ timeout: 15000 });
    await page.getByRole('button', { name: 'Activar Usuario' }).click();
    await expect(page).toHaveURL((url) => url.pathname.endsWith('/admin/users'), { timeout: 15000 });
    await expect(page.getByRole('row', { name: newEmail }).getByText('Activo')).toBeVisible({ timeout: 15000 });
  });

  test('should block duplicate email on creation', async ({ page }) => {
    await page.goto(`${BASE_PATH}/admin/users/create`);

    const authStorageStr = await page.evaluate(() => localStorage.getItem('auth-storage'));
    const tenantId = authStorageStr ? JSON.parse(authStorageStr).state.tenantId : '';

    await page.getByLabel('ID del Tenant').fill(tenantId);
    await page.getByLabel('Nombre Completo').fill('E2E Duplicate');
    await page.getByLabel('Email', { exact: true }).fill(ADMIN_EMAIL); // Use the existing admin email
    await page.getByLabel('Contraseña', { exact: true }).fill('password123');
    await page.locator('select#role').selectOption('CUSTOMER');

    await page.getByRole('button', { name: 'Crear Usuario' }).click();

    await expect(page.getByText('Email already registered globally')).toBeVisible();
  });

  test('should block last superadmin deactivation', async ({ page }) => {
    // Find the admin user and try to edit it
    await page.goto(`${BASE_PATH}/admin/users`);
    await page.getByRole('row', { name: ADMIN_EMAIL }).getByRole('link', { name: 'Editar' }).click();

    await page.getByRole('button', { name: 'Desactivar Usuario' }).click();

    await expect(page.getByText('Cannot deactivate the last active SUPERADMIN')).toBeVisible();
  });
});

/**
 * COMMERCIAL is staff but not SUPERADMIN: it reaches the admin shell but the
 * RoleGuard redirects it to /admin/403. Uses the commercial storageState.
 */
test.describe('Admin Users Management (Non-Superadmin - 403)', () => {
  test.use({ storageState: COMMERCIAL_STATE });

  test('COMMERCIAL role should be redirected to 403 when accessing admin users', async ({ page }) => {
    await page.goto(`${BASE_PATH}/admin/users`);
    await expect(page).toHaveURL((url) => url.pathname.includes('/admin/403'));
    await expect(page.getByRole('heading', { name: 'Acceso denegado' })).toBeVisible();
  });
});
