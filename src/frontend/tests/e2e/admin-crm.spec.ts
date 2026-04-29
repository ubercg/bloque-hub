import { test, expect } from '@playwright/test';

test.describe('CRM - Crear Cotización', () => {
  test.beforeEach(async ({ page }) => {
    // Login como COMMERCIAL
    await page.goto('http://localhost/login');
    await page.fill('input[type="email"]', 'commercial@test.com');
    await page.fill('input[type="password"]', 'password');
    await page.click('button[type="submit"]');
    await page.waitForURL('**/my-events');

    // Ir a CRM
    await page.goto('http://localhost/admin/crm');
  });

  test('debe crear cotización desde modal constructor', async ({ page }) => {
    // Abrir modal
    await page.click('button:has-text("Nueva propuesta")');
    await expect(page.locator('text=Nueva propuesta')).toBeVisible();

    // Seleccionar lead
    const leadSelect = page.locator('select').first();
    await leadSelect.selectOption({ index: 1 }); // Primer lead disponible

    // Agregar item
    await page.click('button:has-text("Añadir")');

    // Llenar fecha (primer input date)
    const dateInput = page.locator('input[type="date"]').first();
    await dateInput.fill('2026-03-15');

    // Crear cotización
    const downloadPromise = page.waitForEvent('download');
    await page.click('button:has-text("Crear cotización")');

    // Verificar toast success
    await expect(page.locator('text=Cotización creada')).toBeVisible({ timeout: 5000 });

    // Verificar descarga de PDF
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/cotizacion-.+\.pdf/);
  });

  test('debe hacer drag-and-drop en Kanban', async ({ page }) => {
    // Verificar que existan columnas
    await expect(page.locator('text=Borrador')).toBeVisible();
    await expect(page.locator('text=Propuesta enviada')).toBeVisible();

    // Esperar a que carguen cotizaciones
    await page.waitForTimeout(1000);

    const firstCard = page.locator('[class*="bg-white"][class*="rounded"]').first();
    if (await firstCard.isVisible()) {
      // Drag de una columna a otra
      const targetColumn = page.locator('text=Propuesta enviada').locator('..');

      await firstCard.dragTo(targetColumn);

      // Verificar toast de actualización
      await expect(page.locator('text=Estado actualizado')).toBeVisible({ timeout: 3000 });
    }
  });
});
