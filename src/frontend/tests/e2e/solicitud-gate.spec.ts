/**
 * E2E Tests: Folio gate — public "Solicitud de Cotización" wizard (REQ-012, PR #6;
 * error states + lead_prefill hydration, REQ-013 Slice D, PR #6).
 *
 * IMPORTANT: this spec runs from the HOST, not inside the frontend Docker
 * container — Playwright browsers cannot run under the Alpine/musl frontend
 * image. Run with `npm run test:e2e` (or the project's Playwright command)
 * from the host machine against a running stack.
 */

import { test, expect, type Page } from '@playwright/test';

// `next.config.ts` hardcodes `basePath: '/bloque'` — every route (incl. this
// one) 404s without the prefix. Matches the convention already used by
// `auth.setup.ts` / `tests/e2e/admin/users.spec.ts`.
const BASE_PATH = '/bloque';
const VALIDATE_FOLIO_URL = '**/quote-requests/validate-folio';
const VALID_FOLIO = 'BCE-20260728-090000-1234';

/** Frozen verbatim (design §7 / Phase 0.3) — no call to action, no alerting claim. */
const AUTH_FAILURE_MESSAGE =
  'No pudimos validar tu folio por una falla de configuración en la integración con BLOQUE Portal. ' +
  'Reintentar no resolverá el problema.';

async function submitFolio(page: Page, folio = VALID_FOLIO): Promise<void> {
  await page.goto(`${BASE_PATH}/solicitud`);
  await page.getByLabel('Folio').fill(folio);
  await page.getByRole('button', { name: 'Continuar' }).click();
}

/**
 * The gate's error `<div role="alert">` — scoped to exclude Next.js's own
 * `#__next-route-announcer__`, which also carries `role="alert"` but is
 * always present (and empty) in the DOM.
 */
function gateAlert(page: Page) {
  return page.locator('[role="alert"]:not(#__next-route-announcer__)');
}

test.describe('Folio gate (/solicitud)', () => {
  test('acceso anónimo a /solicitud NO redirige a /login', async ({ page, context }) => {
    await context.clearCookies();
    await page.goto(`${BASE_PATH}/solicitud`);

    await expect(page).not.toHaveURL(/\/login/);
    await expect(page.getByRole('heading', { name: 'Solicitud de cotización' })).toBeVisible();
  });
});

test.describe('Folio gate — error states (REQ-013 Slice D)', () => {
  test.beforeEach(async ({ context }) => {
    await context.clearCookies();
  });

  test('falla de autenticación de integración muestra copy de sistema, sin CTA de reintento', async ({ page }) => {
    await page.route(VALIDATE_FOLIO_URL, (route) =>
      route.fulfill({
        status: 502,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: { reason: 'INTEGRATION_AUTH_FAILURE', message: 'ignored — Hub copy siempre gana' },
        }),
      })
    );
    await submitFolio(page);

    // Exact-text match verifies the frozen D1 copy, and by construction proves
    // there is no CTA phrase and no claim that an alert was raised (§2.3).
    await expect(gateAlert(page)).toHaveText(AUTH_FAILURE_MESSAGE);
  });

  test('los mensajes de auth-failure, not-eligible y unavailable son textualmente distintos', async ({ page }) => {
    const scenarios: Array<{ status: number; reason: string }> = [
      { status: 502, reason: 'INTEGRATION_AUTH_FAILURE' },
      { status: 403, reason: 'FOLIO_NOT_ELIGIBLE' },
      { status: 503, reason: 'PORTAL_UNAVAILABLE' },
    ];
    const messages: string[] = [];

    for (const { status, reason } of scenarios) {
      await page.route(VALIDATE_FOLIO_URL, (route) =>
        route.fulfill({
          status,
          contentType: 'application/json',
          body: JSON.stringify({ detail: { reason } }),
        })
      );
      await submitFolio(page);
      messages.push((await gateAlert(page).textContent())?.trim() ?? '');
      await page.unroute(VALIDATE_FOLIO_URL);
    }

    expect(new Set(messages).size).toBe(3);
  });

  test('un motivo desconocido cae en unknown_error y NUNCA en el rechazo de folio (regresión :60-61)', async ({
    page,
  }) => {
    await page.route(VALIDATE_FOLIO_URL, (route) =>
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: { reason: 'PORTAL_STATUS_UNMAPPED' } }),
      })
    );
    await submitFolio(page);

    const alert = gateAlert(page);
    await expect(alert).toContainText('Ocurrió un error al validar el folio');
    await expect(alert).not.toContainText('no se encuentra disponible para iniciar una cotización');
  });

  test('status_label del Portal nunca se renderiza en el DOM', async ({ page }) => {
    await page.route(VALIDATE_FOLIO_URL, (route) =>
      route.fulfill({
        status: 403,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: { reason: 'FOLIO_NOT_ELIGIBLE', status_label: 'quotation_rejected_by_portal_team' },
        }),
      })
    );
    await submitFolio(page);

    await expect(gateAlert(page)).toBeVisible();
    await expect(page.locator('body')).not.toContainText('quotation_rejected_by_portal_team');
  });
});

test.describe('Folio gate — éxito con lead_prefill (REQ-013 Slice D)', () => {
  const PREFILL = {
    nombre_completo: 'Ada Lovelace',
    cargo_puesto: 'Directora de Vinculación',
    institucion_organizacion: 'Instituto Analítico',
    correo_institucional: 'ada@instituto.example',
    telefono_contacto: '5555555555',
    asistentes_estimados: 42,
    fecha_tentativa: '2026-09-01',
    tipo_evento_sugerido: null,
    espacio_requerido: 'Auditorio principal',
    requerimientos_especiales: 'Requiere traducción simultánea',
    como_conociste_bloque: null,
  };

  test.beforeEach(async ({ context, page }) => {
    await context.clearCookies();

    await page.route(VALIDATE_FOLIO_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          unlocked: true,
          folio: VALID_FOLIO,
          portal_status: 'quotation_in_progress',
          lead_prefill: PREFILL,
        }),
      })
    );
    await page.route('**/spaces', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'space-1',
            name: 'Auditorio principal',
            slug: 'auditorio-principal',
            capacidad_maxima: 100,
            precio_por_hora: 500,
          },
        ]),
      })
    );
    await page.route('**/pricing-rules', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    );
    await page.route('**/spaces/*/availability**', (route) => {
      const month = new URL(route.request().url()).searchParams.get('month');
      const day = `${month}-15`;
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          month,
          days: { [day]: [{ fecha: day, hora_inicio: '09:00:00', hora_fin: '11:00:00', status: 'AVAILABLE' }] },
        }),
      });
    });
    await page.route('**/quote-requests/price-preview', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [{ price: 1000 }] }),
      })
    );
  });

  test('Step 2 muestra el bloque de referencia sin preseleccionar espacio ni fecha', async ({ page }) => {
    await submitFolio(page);
    await expect(page).toHaveURL(/\/solicitud\/wizard/);

    // Step 1 — asistentes_estimados ya viene hidratado (42); solo se completan
    // los campos que el prefill NO cubre.
    await expect(page.getByLabel('Asistentes estimados')).toHaveValue('42');
    await page.getByLabel('Tipo de evento').selectOption('Conferencia');
    await page.getByLabel('Carácter del evento').selectOption('Privado');
    await page.getByLabel('Descripción del evento').fill('Evento de prueba e2e.');
    await page.getByRole('radio', { name: 'No' }).check();
    await page.getByRole('button', { name: 'Siguiente', exact: true }).click();

    await expect(page.getByRole('heading', { name: /Espacio, fecha y cotización/ })).toBeVisible();

    const referenceBlock = page.getByRole('note', { name: 'Referencia de tu solicitud en BLOQUE Portal' });
    await expect(referenceBlock).toContainText('Fecha tentativa indicada: 2026-09-01');
    await expect(referenceBlock).toContainText('Espacio solicitado: Auditorio principal');

    // Not preselected: no wizard item exists yet (the bandeja only renders once a
    // space is selected or an item exists), and the space card isn't active.
    await expect(page.getByText('Bandeja de cotización')).toHaveCount(0);
    await expect(page.getByRole('button', { name: /Auditorio principal/ })).toHaveAttribute(
      'aria-pressed',
      'false'
    );
  });

  test('el gate exitoso hidrata el store antes de navegar y Step 3 llega pre-llenado y editable', async ({
    page,
  }) => {
    await submitFolio(page);
    await expect(page).toHaveURL(/\/solicitud\/wizard/);

    await page.getByLabel('Tipo de evento').selectOption('Conferencia');
    await page.getByLabel('Carácter del evento').selectOption('Privado');
    await page.getByLabel('Descripción del evento').fill('Evento de prueba e2e.');
    await page.getByRole('radio', { name: 'No' }).check();
    await page.getByRole('button', { name: 'Siguiente', exact: true }).click();

    // Step 2 — add exactly one priced slot to satisfy isStepEspacioValid.
    await page.getByRole('button', { name: 'Auditorio principal' }).click();
    await page.getByRole('button', { name: /^15 de/ }).click();
    await page.getByRole('button', { name: /^09:00 a 11:00/ }).click();
    await expect(page.getByText('$1,000 MXN').first()).toBeVisible();
    await page.getByRole('button', { name: 'Siguiente', exact: true }).click();

    // Step 3 — prefilled from lead_prefill, and still editable.
    await expect(page.getByRole('heading', { name: /Solicitante y documentos/ })).toBeVisible();
    await expect(page.getByLabel('Nombre completo')).toHaveValue(PREFILL.nombre_completo);
    await expect(page.getByLabel('Cargo / puesto')).toHaveValue(PREFILL.cargo_puesto);
    await expect(page.getByLabel('Institución / organización')).toHaveValue(PREFILL.institucion_organizacion);
    await expect(page.getByLabel('Correo institucional')).toHaveValue(PREFILL.correo_institucional);
    await expect(page.getByLabel('Teléfono de contacto')).toHaveValue(PREFILL.telefono_contacto);

    await page.getByLabel('Nombre completo').fill('Nombre Editado Manualmente');
    await expect(page.getByLabel('Nombre completo')).toHaveValue('Nombre Editado Manualmente');
  });
});
