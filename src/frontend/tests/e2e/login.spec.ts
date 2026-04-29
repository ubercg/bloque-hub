/**
 * E2E Tests: Login para Portal del Cliente (Tarea 16.4)
 * Requiere backend con usuarios de prueba (ej. scripts/seed_test_users.py).
 */

import { test, expect } from '@playwright/test';

test.describe('Login', () => {
  test('acceso a ruta protegida sin cookie redirige a /login con redirect', async ({
    page,
    context,
  }) => {
    await context.clearCookies();
    await page.goto('/my-events');
    await expect(page).toHaveURL(/\/login/);
    expect(page.url()).toContain('redirect=');
  });

  test('credenciales inválidas muestran mensaje y permanecen en /login', async ({
    page,
    context,
  }) => {
    await context.clearCookies();
    await page.goto('/login');
    await expect(page.getByRole('heading', { name: 'Iniciar sesión' })).toBeVisible();

    await page.getByLabel(/correo electrónico/i).fill('noexiste@test.com');
    await page.getByLabel(/contraseña/i).fill('wrong');
    await page.getByRole('button', { name: 'Iniciar sesión' }).click();

    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByText('Email o contraseña incorrectos')).toBeVisible();
  });

  test('redirect query: tras login exitoso redirige a la URL indicada', async ({
    page,
    context,
  }) => {
    await context.clearCookies();
    // Usuario de prueba (seed: customer@test.com / password)
    await page.goto('/login?redirect=/catalog');
    await page.getByLabel(/correo electrónico/i).fill('customer@test.com');
    await page.getByLabel(/contraseña/i).fill('password');
    await page.getByRole('button', { name: 'Iniciar sesión' }).click();

    await expect(page).toHaveURL(/\/catalog/);
    const cookies = await context.cookies();
    expect(cookies.some((c) => c.name === 'auth_token' && c.value)).toBeTruthy();
  });

  test('login exitoso como CUSTOMER redirige a /my-events y establece cookie auth_token', async ({
    page,
    context,
  }) => {
    await context.clearCookies();
    await page.goto('/login');
    await page.getByLabel(/correo electrónico/i).fill('customer@test.com');
    await page.getByLabel(/contraseña/i).fill('password');
    await page.getByRole('button', { name: 'Iniciar sesión' }).click();

    await expect(page).toHaveURL(/\/my-events/);
    const cookies = await context.cookies();
    expect(cookies.some((c) => c.name === 'auth_token' && c.value.length > 0)).toBeTruthy();
  });

  test('login exitoso como staff redirige a /admin/dashboard (redirect por rol)', async ({
    page,
    context,
  }) => {
    await context.clearCookies();
    await page.goto('/login');
    await page.getByLabel(/correo electrónico/i).fill('finance@test.com');
    await page.getByLabel(/contraseña/i).fill('password');
    await page.getByRole('button', { name: 'Iniciar sesión' }).click();

    await expect(page).toHaveURL(/\/admin\/dashboard/);
    const cookies = await context.cookies();
    expect(cookies.some((c) => c.name === 'auth_token' && c.value.length > 0)).toBeTruthy();
  });
});
