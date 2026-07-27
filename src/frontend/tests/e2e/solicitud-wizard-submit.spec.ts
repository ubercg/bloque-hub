/**
 * E2E Tests: Wizard Step 5 — legal-acceptance gating (REQ-012, PR #7b, RN-014).
 *
 * IMPORTANT: this spec runs from the HOST, not inside the frontend Docker
 * container — Playwright browsers cannot run under the Alpine/musl frontend
 * image. Run with `npm run test:e2e` (or the project's Playwright command)
 * from the host machine against a running stack, with a valid folio and a
 * completed steps 1-4 state (fixture/setup left to the host test runner).
 */

import { test, expect } from '@playwright/test';

test.describe('Wizard Step 5 — envío (/solicitud/wizard)', () => {
  test('el botón de enviar solicitud permanece deshabilitado hasta aceptar ambas casillas legales', async ({
    page,
  }) => {
    // Setup note: this test assumes a fixture/helper that unlocks the wizard
    // (valid folio) and completes steps 1-4 before reaching Step 5. Adjust to
    // the project's actual fixture helper when wiring this up on the host.
    await page.goto('/solicitud/wizard');

    const submitButton = page.getByRole('button', { name: 'Enviar solicitud' });
    await expect(submitButton).toBeDisabled();

    const infoCheckbox = page.getByText('Confirmo que la información proporcionada es correcta').locator('..').getByRole('checkbox');
    const reglamentoCheckbox = page.getByText('He leído y acepto el').locator('..').getByRole('checkbox');

    await infoCheckbox.check();
    await expect(submitButton).toBeDisabled();

    await reglamentoCheckbox.check();
    await expect(submitButton).toBeEnabled();

    await reglamentoCheckbox.uncheck();
    await expect(submitButton).toBeDisabled();
  });
});
