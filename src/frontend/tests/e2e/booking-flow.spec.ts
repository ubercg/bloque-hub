/**
 * E2E Test: Complete SEMI_DIRECT booking flow
 * Tests the full journey from catalog to voucher upload
 */

import { test, expect } from '@playwright/test';

test.describe('Flujo SEMI_DIRECT completo', () => {
  test.beforeEach(async ({ page, context }) => {
    await page.goto('/');
    await page.evaluate(() => {
      localStorage.setItem('auth_token', 'mock_test_token');
    });
    await context.addCookies([
      { name: 'auth_token', value: 'mock_test_token', path: '/', domain: 'localhost' },
    ]);
  });

  test('debe completar reserva desde catálogo hasta upload de comprobante', async ({ page }) => {
    // 1. Navigate to catalog
    await page.goto('/catalog');
    await expect(page.getByRole('heading', { name: 'Catálogo de Espacios' })).toBeVisible();

    // 2. Wait for spaces to load
    await page.waitForSelector('[data-testid="space-card"]', { timeout: 10000 });

    // 3. Add to cart from first space card (catalog has no detail page)
    const firstSpaceCard = page.locator('[data-testid="space-card"]').first();
    await firstSpaceCard.locator('text=Agregar al carrito').click();

    // 5. Verify cart shows item
    await expect(page.locator('text=Bandeja de Evento')).toBeVisible();

    // 6. Navigate to confirmation
    await page.locator('button:has-text("Continuar con Reserva")').click();

    // 7. Verify we're on confirm page
    await expect(page).toHaveURL(/\/booking\/confirm/);
    await expect(page.locator('h1')).toContainText('Confirmar Reserva');

    // 8. Fill contact form
    await page.fill('input[name="nombre_contacto"]', 'Test Usuario E2E');
    await page.fill('input[name="email"]', 'test-e2e@bloque.example');
    await page.fill('input[name="telefono"]', '5512345678');
    await page.selectOption('select[name="tipo_cliente"]', 'B2B');

    // 9. Submit reservation
    await page.locator('button[type="submit"]:has-text("Crear Reserva")').click();

    // 10. Verify success redirect
    await expect(page).toHaveURL(/\/booking\/success/, { timeout: 15000 });

    // 11. Extract reservation ID from URL
    const url = page.url();
    const reservationId = new URLSearchParams(new URL(url).search).get('id');
    expect(reservationId).toBeTruthy();

    // 12. Navigate to upload voucher page
    await page.goto(`/booking/upload-voucher?id=${reservationId}`);

    // 13. Verify upload page loaded
    await expect(page.locator('h1')).toContainText('Subir Comprobante de Pago');

    // 14. Upload a file (create mock PDF in test)
    const fileInput = page.locator('input[type="file"]');

    // Create a mock PDF file
    const mockPdfContent = '%PDF-1.4\nTest payment voucher content\n%%EOF';
    const buffer = Buffer.from(mockPdfContent);

    await fileInput.setInputFiles({
      name: 'comprobante-test.pdf',
      mimeType: 'application/pdf',
      buffer: buffer,
    });

    // 15. Verify file was selected
    await expect(page.locator('text=comprobante-test.pdf')).toBeVisible();

    // 16. Click upload button
    await page.locator('button:has-text("Confirmar y Subir")').click();

    // 17. Verify success message (or wait for redirect)
    await expect(page.locator('text=¡Comprobante recibido!')).toBeVisible({ timeout: 10000 });

    // 18. Verify TTL freeze message
    await expect(page.locator('text=protegida')).toBeVisible();
  });

  test('debe mostrar error al subir archivo muy grande', async ({ page }) => {
    // Navigate directly to upload page (assuming we have a reservation ID)
    await page.goto('/booking/upload-voucher?id=test-reservation-id');

    // Try to upload a file > 10MB (mock)
    const fileInput = page.locator('input[type="file"]');

    // Create a file that's "too large" (11MB worth of data)
    const largeBuffer = Buffer.alloc(11 * 1024 * 1024, 'x');

    await fileInput.setInputFiles({
      name: 'large-file.pdf',
      mimeType: 'application/pdf',
      buffer: largeBuffer,
    });

    // Verify error message appears
    await expect(page.locator('text=/archivo es muy grande/i')).toBeVisible();
  });

  test('debe mostrar error al subir archivo muy pequeño', async ({ page }) => {
    await page.goto('/booking/upload-voucher?id=test-reservation-id');

    const fileInput = page.locator('input[type="file"]');

    // Create a file < 5KB
    const tinyBuffer = Buffer.from('tiny');

    await fileInput.setInputFiles({
      name: 'tiny.pdf',
      mimeType: 'application/pdf',
      buffer: tinyBuffer,
    });

    // Verify error message
    await expect(page.locator('text=/archivo es muy pequeño/i')).toBeVisible();
  });

  test('debe rechazar tipo de archivo inválido', async ({ page }) => {
    await page.goto('/booking/upload-voucher?id=test-reservation-id');

    const fileInput = page.locator('input[type="file"]');

    // Try to upload a .txt file
    const txtBuffer = Buffer.from('This is a text file');

    await fileInput.setInputFiles({
      name: 'invalid.txt',
      mimeType: 'text/plain',
      buffer: txtBuffer,
    });

    // Verify error message (client-side validation)
    await expect(page.getByText(/Tipo de archivo no permitido|no permitido/i)).toBeVisible({ timeout: 5000 });
  });
});

test.describe('Navegación "El Elevador"', () => {
  test('debe permitir navegar entre pisos', async ({ page }) => {
    await page.goto('/catalog');

    // Verify sidebar is visible
    await expect(page.locator('text=Navegación por pisos')).toBeVisible();

    // Click on Piso 3
    await page.locator('button:has-text("Piso 3")').click();

    // Verify active state
    const piso3Button = page.locator('button:has-text("Piso 3")');
    await expect(piso3Button).toHaveClass(/bg-blue-600/);

    // Use elevator controls to go up
    await page.locator('button[title="Subir piso"]').click();

    // Verify Piso 4 is now active
    const piso4Button = page.locator('button:has-text("Piso 4")');
    await expect(piso4Button).toHaveClass(/bg-blue-600/);

    // Go down
    await page.locator('button[title="Bajar piso"]').click();

    // Should be back to Piso 3
    await expect(piso3Button).toHaveClass(/bg-blue-600/);
  });
});
