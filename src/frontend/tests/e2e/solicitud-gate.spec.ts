/**
 * E2E Tests: Folio gate — public "Solicitud de Cotización" wizard (REQ-012, PR #6).
 *
 * IMPORTANT: this spec runs from the HOST, not inside the frontend Docker
 * container — Playwright browsers cannot run under the Alpine/musl frontend
 * image. Run with `npm run test:e2e` (or the project's Playwright command)
 * from the host machine against a running stack.
 */

import { test, expect } from '@playwright/test';

test.describe('Folio gate (/solicitud)', () => {
  test('acceso anónimo a /solicitud NO redirige a /login', async ({ page, context }) => {
    await context.clearCookies();
    await page.goto('/solicitud');

    await expect(page).not.toHaveURL(/\/login/);
    await expect(page.getByRole('heading', { name: 'Solicitud de cotización' })).toBeVisible();
  });
});
