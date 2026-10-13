import { expect, test } from '@playwright/test';

const routes = [
  { path: '/#/dashboard', heading: 'Patient Monitoring Overview' },
  { path: '/#/patients', heading: 'Patients' },
  { path: '/#/alerts', heading: 'Alert Operations Center', navLabel: 'Alerts' },
  { path: '/#/analytics', heading: 'Analytics' },
  { path: '/#/settings', heading: 'Settings' },
];

async function signIn(page) {
  // Keep E2E deterministic and independent of production credentials/secrets.
  await page.route('**/api/v1/auth/login', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ access_token: 'e2e-test-token', token_type: 'bearer', expires_in: 900, username: 'e2e-operator', role: 'admin', full_name: 'E2E Operator' }),
    });
  });
  await page.goto('/#/login');
  await page.getByLabel('Username').fill('e2e-operator');
  await page.getByLabel('Password').fill('e2e-test-password');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/#\/dashboard$/);
}

test('all primary routes render and survive a browser reload', async ({ page }) => {
  await signIn(page);
  for (const route of routes) {
    await page.goto(route.path);
    const expectedUrl = new URL(route.path, process.env.E2E_BASE_URL || 'http://127.0.0.1:4173').toString();
    await expect(page).toHaveURL(expectedUrl);
    await expect(page.locator('#main-content')).toBeVisible();
    await expect(page.locator('#main-content').getByRole('heading', { name: route.heading, exact: true }).first()).toBeVisible();

    await page.reload();
    await expect(page).toHaveURL(expectedUrl);
    await expect(page.locator('#main-content')).toBeVisible();
    await expect(page.locator('#main-content').getByRole('heading', { name: route.heading, exact: true }).first()).toBeVisible();
  }
});

test('primary navigation moves between core workspaces', async ({ page }) => {
  await signIn(page);
  const navigation = page.getByRole('navigation', { name: 'Primary' });
  for (const route of routes.slice(1)) {
    await navigation.getByRole('link', { name: route.navLabel ?? route.heading, exact: false }).click();
    await expect(page.locator('#main-content').getByRole('heading', { name: route.heading, exact: true }).first()).toBeVisible();
  }
});

test('mobile navigation opens and routes to Settings', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page);
  await page.getByRole('button', { name: 'Open navigation menu' }).click();
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('link', { name: 'Settings', exact: false }).click();
  await expect(page.locator('#main-content').getByRole('heading', { name: 'Settings', exact: true }).first()).toBeVisible();
});
