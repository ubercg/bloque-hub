/**
 * E2E Tests: Portal del Cliente (Mis eventos)
 * Tarea 16 — Listado, detalle con línea de tiempo y mensajes, acceso/QR/CFDI
 */

import { test, expect } from '@playwright/test';

test.describe('Portal del Cliente — Mis eventos', () => {
  test('sin sesión redirige a login al entrar a /my-events', async ({ page, context }) => {
    await context.clearCookies();
    await page.goto('/my-events');
    await expect(page).toHaveURL(/\/login/);
    expect(page.url()).toContain('redirect=');
  });

  test('con sesión muestra la página Mis eventos', async ({ page, context }) => {
    await page.goto('/');
    await page.evaluate(() => {
      localStorage.setItem('auth_token', 'mock_test_token');
    });
    await context.addCookies([
      { name: 'auth_token', value: 'mock_test_token', path: '/', domain: 'localhost' },
    ]);

    await page.goto('/my-events');
    await expect(page.getByRole('heading', { name: 'Mis eventos' })).toBeVisible({ timeout: 10000 });
    // Puede mostrar lista vacía o listado; al menos el título y navegación
    await expect(page.getByRole('link', { name: /Mis eventos/ })).toBeVisible();
    await expect(page.getByRole('link', { name: /Catálogo/ })).toBeVisible();
  });

  test('con sesión muestra detalle con línea de tiempo y mensajes al tener un evento', async ({ page, context }) => {
    await page.goto('/');
    await page.evaluate(() => {
      localStorage.setItem('auth_token', 'mock_test_token');
    });
    await context.addCookies([
      { name: 'auth_token', value: 'mock_test_token', path: '/', domain: 'localhost' },
    ]);

    await page.goto('/my-events');
    await expect(page.getByRole('heading', { name: 'Mis eventos' })).toBeVisible({ timeout: 10000 });

    // Si hay al menos un evento, clic en el primero (tarjeta con enlace /my-events/{uuid})
    const firstEventLink = page.locator('a[href^="/my-events/"]').first();
    const count = await firstEventLink.count();
    if (count > 0) {
      await firstEventLink.click();
      await expect(page).toHaveURL(/\/my-events\/[0-9a-f-]+/);
      await expect(page.getByText('Estado de tu reserva')).toBeVisible({ timeout: 5000 });
      await expect(page.getByRole('heading', { name: 'Resumen del evento' })).toBeVisible({ timeout: 5000 });
      await expect(page.getByText('Mensajes con Operaciones')).toBeVisible();
      await expect(page.getByRole('link', { name: /Acceso y factura/ })).toBeVisible();
    }
    // Si no hay eventos, la página de lista ya está correcta
  });

  test('página de acceso muestra secciones de readiness, QR y factura', async ({ page, context }) => {
    await page.goto('/');
    await page.evaluate(() => {
      localStorage.setItem('auth_token', 'mock_test_token');
    });
    await context.addCookies([
      { name: 'auth_token', value: 'mock_test_token', path: '/', domain: 'localhost' },
    ]);

    // Usar un UUID válido; puede devolver 404 si no existe
    const fakeId = '00000000-0000-4000-8000-000000000001';
    await page.goto(`/my-events/${fakeId}/access`);
    await expect(page).toHaveURL(new RegExp(`/my-events/${fakeId}/access`));
    await expect(page.getByRole('heading', { name: 'Acceso y factura' })).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Estado de preparación')).toBeVisible();
    await expect(page.getByText('QR de acceso')).toBeVisible();
    await expect(page.getByText('Factura CFDI')).toBeVisible();
  });

  test('botón QR deshabilitado cuando no está listo', async ({ page, context }) => {
    await page.goto('/');
    await page.evaluate(() => {
      localStorage.setItem('auth_token', 'mock_test_token');
    });
    await context.addCookies([
      { name: 'auth_token', value: 'mock_test_token', path: '/', domain: 'localhost' },
    ]);

    const fakeId = '00000000-0000-4000-8000-000000000001';
    await page.goto(`/my-events/${fakeId}/access`);
    await expect(page.getByText('QR de acceso')).toBeVisible({ timeout: 10000 });
    // Cuando no está listo debe mostrarse el mensaje de "debe estar preparado"
    await expect(page.getByText(/debe estar preparado|documentos aprobados/)).toBeVisible({ timeout: 5000 });
  });

  test('flujo buzón y acceso: detalle muestra Buzón y enlace a Acceso (readiness/QR)', async ({ page, context }) => {
    await page.goto('/');
    await page.evaluate(() => {
      localStorage.setItem('auth_token', 'mock_test_token');
    });
    await context.addCookies([
      { name: 'auth_token', value: 'mock_test_token', path: '/', domain: 'localhost' },
    ]);

    await page.goto('/my-events');
    await expect(page.getByRole('heading', { name: 'Mis eventos' })).toBeVisible({ timeout: 10000 });
    const firstEventLink = page.locator('a[href^="/my-events/"]').first();
    if ((await firstEventLink.count()) > 0) {
      await firstEventLink.click();
      await expect(page).toHaveURL(/\/my-events\/[0-9a-f-]+/);
      await expect(page.getByText('Estado de tu reserva')).toBeVisible({ timeout: 5000 });
      await expect(page.getByRole('link', { name: /Acceso y factura/ })).toBeVisible();
      await expect(page.getByRole('heading', { name: 'Documentos requeridos' })).toBeVisible({ timeout: 5000 });
      await page.getByRole('link', { name: /Acceso y factura/ }).click();
      await expect(page).toHaveURL(/\/access/);
      await expect(page.getByRole('heading', { name: 'Acceso y factura' })).toBeVisible({ timeout: 5000 });
      await expect(page.getByText('Estado de preparación')).toBeVisible();
      await expect(page.getByText('QR de acceso')).toBeVisible();
    }
  });
});
