// The Content-Security-Policy allows no inline script and no inline style (X2): every page of both sites, and the
// canvas with each tab of its panel, opens without one violation (watch() hears them), under the policy the server sends.

import { expect, test, type Cookie, type Page } from '@playwright/test';
import { CONSOLE } from '../../playwright.config';
import { ACCOUNTS } from './accounts';
import { seedCanvas, type Seeded } from './seed';
import { signIn } from './signin';
import { watch } from './watch';

let seeded: Seeded;
test.beforeAll(async ({ browser }) => {
  const page = await browser.newPage();
  await signIn(page);
  seeded = await seedCanvas(page, 'Canvas test');
  await page.close();
});

async function visit(page: Page, url: string) {
  const answer = await page.goto(url);
  const policy = answer?.headers()['content-security-policy'] ?? '';
  expect(policy).toContain("style-src 'self';");
  expect(policy).not.toContain('unsafe-inline');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(600); // the landing's scenes and the charts draw a moment after
}

test('the studio: every page, the landing and its scenes, the canvas and its panel', async ({ page }) => {
  const problems = watch(page);
  for (const path of ['/', '/signin', '/signup']) await visit(page, path);
  await signIn(page);
  for (const path of ['/home', '/projects', '/library', '/skills', '/guide', '/settings', '/create'])
    await visit(page, path);
  await visit(page, `/project/${seeded.ref}`);
  await visit(page, `/analytics/${seeded.ref}`);
  await visit(page, `/canvas/${seeded.ref}`);
  const panel = page.getByRole('complementary', { name: 'Make something' });
  for (const tab of ['Quick actions', 'Agent', 'NeuralCore']) {
    await panel.getByRole('button', { name: tab, exact: true }).click();
    await page.waitForTimeout(400);
  }
  expect(problems).toEqual([]);
});

let kept: Cookie[] | null = null;
test('the console: every section', async ({ page }) => {
  const problems = watch(page);
  await visit(page, `${CONSOLE}/signin`);
  const { email, password } = ACCOUNTS.admin;
  const answer = await page.request.post(CONSOLE + '/api/console/login', { data: { email, password } });
  expect(answer.ok()).toBe(true);
  kept = await page.context().cookies();
  await page.context().addCookies(kept);
  for (const section of [
    'overview',
    'jobs',
    'system',
    'users',
    'credits',
    'pricing',
    'economics',
    'workflows',
    'agent',
  ])
    await visit(page, `${CONSOLE}/${section}`);
  for (const section of ['library', 'projects', 'moderation', 'skills', 'showcase', 'endpoints', 'roles', 'audit'])
    await visit(page, `${CONSOLE}/${section}`);
  await visit(page, `${CONSOLE}/settings`);
  await visit(page, `${CONSOLE}/sessions`);
  expect(problems).toEqual([]);
});
