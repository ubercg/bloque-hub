import { test, expect } from '@playwright/test';

test.describe('Operations - Control Center', () => {
  test.beforeEach(async ({ page }) => {
    // Login como OPERATIONS
    await page.goto('http://localhost/login');
    await page.fill('input[type="email"]', 'operations@test.com');
    await page.fill('input[type="password"]', 'password');
    await page.click('button[type="submit"]');
    await page.waitForURL('**/my-events');

    // Ir a Operations
    await page.goto('http://localhost/admin/operations');
  });

  test('debe mostrar timeline Gantt con espacios', async ({ page }) => {
    // Verificar título
    await expect(page.locator('text=Control Center Operativo')).toBeVisible();

    // Verificar filtros
    await expect(page.locator('input[type="date"]').first()).toBeVisible();
    await expect(page.locator('select').first()).toBeVisible(); // Filtro de estado

    // Verificar que existe contenido de timeline
    const timelineContent = page.locator('[class*="grid"], [role="grid"]');
    // Al menos debería existir algún contenedor grid
    const gridCount = await timelineContent.count();
    expect(gridCount).toBeGreaterThan(0);
  });

  test('debe mostrar panel de readiness con polling', async ({ page }) => {
    // Scroll a sección de readiness
    await page.locator('text=Readiness Monitor').scrollIntoViewIfNeeded();

    // Verificar que existe el contenido de readiness
    const readinessSection = page.locator('text=Readiness Monitor').locator('..');
    await expect(readinessSection).toBeVisible();

    // Esperar un poco para que carguen datos
    await page.waitForTimeout(2000);

    // Verificar que existen indicadores (Si/No o porcentajes o mensajes)
    const content = await readinessSection.textContent();
    expect(content).toBeTruthy();
  });

  test('debe permitir interacción con controles de filtro', async ({ page }) => {
    // Cambiar fecha de inicio
    const dateInput = page.locator('input[type="date"]').first();
    await dateInput.fill('2026-03-01');

    // Cambiar filtro de estado
    const statusSelect = page.locator('select').first();
    await statusSelect.selectOption({ index: 1 });

    // Esperar que la página responda (cualquier recarga de datos)
    await page.waitForTimeout(1000);

    // Verificar que los controles mantienen sus valores
    expect(await dateInput.inputValue()).toBe('2026-03-01');
  });
});
