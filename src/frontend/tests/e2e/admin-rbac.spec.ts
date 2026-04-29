import { test, expect } from '@playwright/test';

test.describe('RBAC - Role-Based Access Control', () => {
  test('COMMERCIAL no puede acceder a Finance', async ({ page }) => {
    // Login como COMMERCIAL
    await page.goto('http://localhost/login');
    await page.fill('input[type="email"]', 'commercial@test.com');
    await page.fill('input[type="password"]', 'password');
    await page.click('button[type="submit"]');
    await page.waitForURL('**/my-events');

    // Intentar acceder a Finance
    await page.goto('http://localhost/admin/finance');

    // Debe redirigir a 403
    await expect(page).toHaveURL(/\/admin\/403/);
    await expect(page.locator('text=/Acceso denegado|No tienes permisos/i')).toBeVisible();
  });

  test('OPERATIONS no puede acceder a CRM', async ({ page }) => {
    // Login como OPERATIONS
    await page.goto('http://localhost/login');
    await page.fill('input[type="email"]', 'operations@test.com');
    await page.fill('input[type="password"]', 'password');
    await page.click('button[type="submit"]');
    await page.waitForURL('**/my-events');

    // Intentar acceder a CRM
    await page.goto('http://localhost/admin/crm');

    // Debe redirigir a 403
    await expect(page).toHaveURL(/\/admin\/403/);
  });

  test('FINANCE no puede acceder a Settings', async ({ page }) => {
    // Login como FINANCE
    await page.goto('http://localhost/login');
    await page.fill('input[type="email"]', 'finance@test.com');
    await page.fill('input[type="password"]', 'password');
    await page.click('button[type="submit"]');
    await page.waitForURL('**/my-events');

    // Intentar acceder a Settings
    await page.goto('http://localhost/admin/settings');

    // Debe redirigir a 403
    await expect(page).toHaveURL(/\/admin\/403/);
  });

  test('SUPERADMIN puede acceder a todos los módulos', async ({ page }) => {
    // Login como SUPERADMIN
    await page.goto('http://localhost/login');
    await page.fill('input[type="email"]', 'admin@test.com');
    await page.fill('input[type="password"]', 'password');
    await page.click('button[type="submit"]');
    await page.waitForURL('**/my-events');

    // Verificar acceso a todos los módulos
    const modules = [
      { path: '/admin/crm', text: 'CRM' },
      { path: '/admin/operations', text: 'Control Center' },
      { path: '/admin/finance', text: 'Finanzas' },
      { path: '/admin/settings', text: 'Ajustes' },
    ];

    for (const module of modules) {
      await page.goto(`http://localhost${module.path}`);
      await expect(page).toHaveURL(module.path);
      await expect(page.locator(`text=${module.text}`)).toBeVisible();
    }
  });

  test('sidebar muestra solo módulos permitidos según rol', async ({ page }) => {
    // Login como COMMERCIAL
    await page.goto('http://localhost/login');
    await page.fill('input[type="email"]', 'commercial@test.com');
    await page.fill('input[type="password"]', 'password');
    await page.click('button[type="submit"]');
    await page.waitForURL('**/my-events');

    await page.goto('http://localhost/admin/crm');

    // Sidebar debe mostrar solo CRM
    const sidebar = page.locator('nav, aside').filter({ hasText: 'CRM' });
    await expect(sidebar.locator('text=CRM')).toBeVisible();

    // NO debe mostrar otros módulos (verificar que no existe texto)
    const sidebarText = await sidebar.textContent();
    expect(sidebarText).not.toContain('Control Center');
    expect(sidebarText).not.toContain('Finanzas');
    expect(sidebarText).not.toContain('Ajustes');
  });
});
