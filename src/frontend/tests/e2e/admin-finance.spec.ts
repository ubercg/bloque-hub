import { test, expect } from '@playwright/test';
import fs from 'fs';
import path from 'path';

test.describe('Finance - Conciliación y Export', () => {
  test.beforeEach(async ({ page }) => {
    // Login como FINANCE
    await page.goto('http://localhost/login');
    await page.fill('input[type="email"]', 'finance@test.com');
    await page.fill('input[type="password"]', 'password');
    await page.click('button[type="submit"]');
    await page.waitForURL('**/my-events');

    // Ir a Finance
    await page.goto('http://localhost/admin/finance');
  });

  test('debe aprobar pago con modal de confirmación', async ({ page }) => {
    // Verificar tabla de revisión
    const table = page.locator('table').first();
    await expect(table).toBeVisible();

    // Si hay reservas en revisión
    const approveBtn = page.locator('button:has-text("Aprobar")').first();
    if (await approveBtn.isVisible()) {
      await approveBtn.click();

      // Modal de confirmación
      await expect(page.locator('text=Confirmar aprobación de pago')).toBeVisible();

      // Confirmar
      await page.click('button:has-text("Aprobar")'); // Botón dentro del modal

      // Verificar toast
      await expect(page.locator('text=Pago aprobado')).toBeVisible({ timeout: 5000 });
    }
  });

  test('debe rechazar pago con motivo opcional', async ({ page }) => {
    const rejectBtn = page.locator('button:has-text("Rechazar")').first();
    if (await rejectBtn.isVisible()) {
      await rejectBtn.click();

      // Modal de confirmación
      await expect(page.locator('text=Confirmar rechazo de pago')).toBeVisible();

      // Llenar motivo
      await page.fill('input[placeholder="Motivo del rechazo"]', 'Comprobante incorrecto');

      // Confirmar
      await page.click('button:has-text("Rechazar")'); // Botón dentro del modal

      // Verificar toast
      await expect(page.locator('text=Pago rechazado')).toBeVisible({ timeout: 5000 });
    }
  });

  test('debe exportar CSV con formato correcto (valida Fix 1.1)', async ({ page }) => {
    // Configurar descarga
    const downloadPromise = page.waitForEvent('download');

    // Clic en exportar
    await page.click('button:has-text("Exportar reporte (CSV)")');

    // Verificar toast
    await expect(page.locator('text=Exportado')).toBeVisible();

    // Descargar archivo
    const download = await downloadPromise;
    const downloadsDir = path.join(__dirname, '../../../downloads');
    if (!fs.existsSync(downloadsDir)) {
      fs.mkdirSync(downloadsDir, { recursive: true });
    }
    const filePath = path.join(downloadsDir, download.suggestedFilename());
    await download.saveAs(filePath);

    // Leer CSV
    const csvContent = fs.readFileSync(filePath, 'utf-8');
    const lines = csvContent.split('\n');

    // Verificar header
    expect(lines[0]).toBe('id,fecha,hora,status');

    // Verificar que columna hora NO contenga "undefined"
    if (lines.length > 1) {
      const dataLine = lines[1];
      expect(dataLine).not.toContain('undefined');
      expect(dataLine).toMatch(/,\d{2}:\d{2}-\d{2}:\d{2},/); // Formato "09:00-11:00"
    }

    // Limpiar archivo de test
    fs.unlinkSync(filePath);
  });

  test('debe mostrar créditos y abrir modal de aplicación', async ({ page }) => {
    // Scroll a sección de créditos
    await page.locator('text=Notas de crédito').scrollIntoViewIfNeeded();

    // Verificar tabla de créditos
    const creditsTable = page.locator('table').nth(1);
    await expect(creditsTable).toBeVisible();

    // Si hay créditos con saldo
    const applyBtn = page.locator('button:has-text("Aplicar")').first();
    if (await applyBtn.isVisible()) {
      await applyBtn.click();

      // Verificar modal de aplicación
      await expect(page.locator('text=Aplicar crédito a reserva')).toBeVisible();
      await expect(page.locator('select')).toBeVisible(); // Selector de reserva
      await expect(page.locator('input[type="number"]')).toBeVisible(); // Monto

      // Cerrar modal
      await page.click('button:has-text("Cancelar")');
    }
  });
});
