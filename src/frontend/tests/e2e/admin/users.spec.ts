import { test, expect, Page, BrowserContext } from '@playwright/test';

const BASE_PATH = '/bloque'; 
const ADMIN_EMAIL = 'admin@test.com';
const ADMIN_PASSWORD = 'password';
const COMMERCIAL_EMAIL = 'commercial@test.com';
const COMMERCIAL_PASSWORD = 'password';

async function login(page: Page, context: BrowserContext, email: string, password: string) {
  await context.clearCookies();
  await page.goto(`${BASE_PATH}/login`);
  await page.waitForTimeout(2000); // Wait for React hydration
  await page.getByLabel('Correo electrónico').fill(email);
  await page.getByLabel('Contraseña').fill(password);
  await page.getByRole('button', { name: 'Iniciar sesión' }).click();
  await page.waitForURL(url => url.pathname.includes('/admin') || url.pathname.includes('/my-events'), { timeout: 15000 });
}

test.describe('Admin Users Management (Superadmin)', () => {
  test.beforeEach(async ({ page, context }) => {
    await login(page, context, ADMIN_EMAIL, ADMIN_PASSWORD);
  });

  test('should display a list of users and navigate to create', async ({ page }) => {
    await page.goto(`${BASE_PATH}/admin/users`);
    await expect(page.getByRole('heading', { name: 'Administración de Usuarios' })).toBeVisible({ timeout: 15000 });
    
    // Check if there's at least one user in the list (the admin themselves)
    await expect(page.getByRole('cell', { name: ADMIN_EMAIL })).toBeVisible({ timeout: 15000 });

    await page.getByRole('link', { name: 'Nuevo Usuario' }).click();
    await expect(page).toHaveURL(url => url.pathname.includes('/admin/users/create'));
  });

  test('should allow creating a new user and deleting it', async ({ page, context }) => {
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

    // Verify it navigates back and the user is created
    await expect(page).toHaveURL(url => url.pathname.endsWith('/admin/users'));
    await expect(page.getByRole('cell', { name: newEmail })).toBeVisible();

    // Now edit and deactivate it
    await page.getByRole('row', { name: newEmail }).getByRole('link', { name: 'Editar' }).click();
    await expect(page.getByRole('heading', { name: 'Editar Usuario: E2E Test User' })).toBeVisible();
    
    await page.getByRole('button', { name: 'Desactivar Usuario' }).click();
    await expect(page).toHaveURL(url => url.pathname.endsWith('/admin/users'));
    await expect(page.getByRole('row', { name: newEmail }).getByText('Inactivo')).toBeVisible();

    // Reactivate
    await page.getByRole('row', { name: newEmail }).getByRole('link', { name: 'Editar' }).click();
    await expect(page.getByRole('heading', { name: 'Editar Usuario: E2E Test User' })).toBeVisible();
    await page.getByRole('button', { name: 'Activar Usuario' }).click();
    await expect(page).toHaveURL(url => url.pathname.endsWith('/admin/users'));
    await expect(page.getByRole('row', { name: newEmail }).getByText('Activo')).toBeVisible();
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

test.describe('Admin Users Management (Non-Superadmin - 403)', () => {
  test('COMMERCIAL role should be redirected to 403 when accessing admin users', async ({ page, context }) => {
    await login(page, context, COMMERCIAL_EMAIL, COMMERCIAL_PASSWORD);
    await expect(page).toHaveURL(url => url.pathname.includes('/my-events') || url.pathname.includes('/catalog') || url.pathname.includes('/admin/dashboard'));

    await page.goto(`${BASE_PATH}/admin/users`); 
    await expect(page).toHaveURL(url => url.pathname.includes('/admin/403'));
    await expect(page.getByRole('heading', { name: 'Acceso denegado' })).toBeVisible();
  });
});
