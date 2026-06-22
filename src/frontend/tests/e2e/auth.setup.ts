import { test as setup } from '@playwright/test';

import { ADMIN_STATE, COMMERCIAL_STATE } from './auth-paths';

/**
 * Auth setup project: logs in once per role via the UI and persists the
 * authenticated storageState (cookie + localStorage). Test projects reuse these
 * files instead of logging in per-test, which removes the concurrent-login race
 * that made the suite flaky under parallel workers.
 */

// Run the two role logins serially: under dev-mode (Turbopack) the first compile
// of /login is slow, and two concurrent logins can time out.
setup.describe.configure({ mode: 'serial' });

const BASE_PATH = '/bloque';

async function uiLogin(
  page: import('@playwright/test').Page,
  email: string,
  password: string,
) {
  await page.goto(`${BASE_PATH}/login`);
  await page.getByLabel('Correo electrónico').fill(email);
  await page.getByLabel('Contraseña').fill(password);
  await page.getByRole('button', { name: 'Iniciar sesión' }).click();
  await page.waitForURL(
    (url) => url.pathname.includes('/admin') || url.pathname.includes('/my-events'),
    { timeout: 15000 },
  );
  // Let role hydration (GET /me) settle so the saved state includes the role.
  await page.waitForLoadState('networkidle');
}

setup('authenticate as superadmin', async ({ page }) => {
  await uiLogin(page, 'admin@test.com', 'password');
  await page.context().storageState({ path: ADMIN_STATE });
});

setup('authenticate as commercial', async ({ page }) => {
  await uiLogin(page, 'commercial@test.com', 'password');
  await page.context().storageState({ path: COMMERCIAL_STATE });
});
