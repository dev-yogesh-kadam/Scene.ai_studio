// Every page of the studio and the console, and the windows they open, checked by axe-core: no serious or critical
// accessibility problem (contrast, names of buttons and fields, roles, labels, landmarks...).

import { expect, test, type Cookie, type Page } from '@playwright/test';
import { CONSOLE } from '../../playwright.config';
import { ACCOUNTS } from './accounts';
import { axe } from './axe';
import { seedCanvas, type Seeded } from './seed';
import { signIn } from './signin';

let seeded: Seeded;
test.beforeAll(async ({ browser }) => {
  const page = await browser.newPage();
  await signIn(page);
  seeded = await seedCanvas(page, 'Canvas test');
  await page.close();
});

/** The page as it is once what it loads has come: the network quiet and nothing moving in. */
async function settled(page: Page) {
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(400);
}

test('the pages of someone not signed in', async ({ page }) => {
  const problems: string[] = [];
  for (const path of ['/', '/signin', '/signup']) {
    await page.goto(path);
    await settled(page);
    problems.push(...(await axe(page, path)));
  }
  expect(problems).toEqual([]);
});

test('the pages of the studio', async ({ page }) => {
  await signIn(page);
  const problems: string[] = [];
  for (const path of ['/home', '/projects', '/library', '/skills', '/guide', '/settings', '/create']) {
    await page.goto(path);
    await settled(page);
    problems.push(...(await axe(page, path)));
  }
  await page.goto(`/project/${seeded.ref}`);
  await settled(page);
  problems.push(...(await axe(page, 'a project')));
  await page.goto(`/analytics/${seeded.ref}`);
  await settled(page);
  problems.push(...(await axe(page, 'analytics')));
  expect(problems).toEqual([]);
});

test('the canvas: each tab of the panel, a frame selected, the library drawer', async ({ page }) => {
  await signIn(page);
  const problems: string[] = [];
  await page.goto(`/canvas/${seeded.ref}`);
  await expect(page.getByText('4 items')).toBeVisible({ timeout: 15_000 });
  const panel = page.getByRole('complementary', { name: 'Make something' });
  for (const tab of ['Quick actions', 'Agent', 'NeuralCore']) {
    await panel.getByRole('button', { name: tab, exact: true }).click();
    await settled(page);
    problems.push(...(await axe(page, `canvas, ${tab}`)));
  }
  await page.getByTitle('Second', { exact: true }).first().click();
  problems.push(...(await axe(page, 'canvas, a frame selected')));
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Library', exact: true }).first().click();
  await expect(page.getByRole('dialog', { name: 'Library' })).toBeVisible();
  await settled(page);
  problems.push(...(await axe(page, 'canvas, library drawer')));
  expect(problems).toEqual([]);
});

test('the windows: the viewer, a question, a new project, sharing', async ({ page }) => {
  await signIn(page);
  const problems: string[] = [];
  await page.goto('/library');
  await settled(page);
  await page.getByRole('article').first().locator('[data-picture]').click();
  await expect(page.getByRole('dialog', { name: 'Viewer' })).toBeVisible();
  await settled(page);
  problems.push(...(await axe(page, 'the viewer')));
  await page.keyboard.press('Escape');

  await page.goto('/projects');
  await settled(page);
  await page
    .getByRole('button', { name: /New project|Create your first project/ })
    .first()
    .click();
  await expect(page.getByRole('dialog')).toBeVisible();
  problems.push(...(await axe(page, 'new project')));
  await page.keyboard.press('Escape');

  await page.goto(`/canvas/${seeded.ref}`);
  await expect(page.getByText('4 items')).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name: /Share/ }).first().click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await settled(page);
  problems.push(...(await axe(page, 'sharing')));
  await page.keyboard.press('Escape');

  await page.goto(`/project/${seeded.ref}`);
  await settled(page);
  await page
    .getByRole('button', { name: /Delete/ })
    .first()
    .click();
  await expect(page.getByRole('dialog')).toBeVisible();
  problems.push(...(await axe(page, 'a question (delete)')));
  await page.keyboard.press('Escape');
  expect(problems).toEqual([]);
});

let kept: Cookie[] | null = null;
async function openConsole(page: Page, section: string) {
  if (kept) await page.context().addCookies(kept);
  else {
    const { email, password } = ACCOUNTS.admin;
    const answer = await page.request.post(CONSOLE + '/api/console/login', { data: { email, password } });
    expect(answer.ok()).toBe(true);
    kept = await page.context().cookies();
  }
  await page.goto(`${CONSOLE}/${section}`);
  await settled(page);
}

const SECTIONS = [
  'overview',
  'jobs',
  'system',
  'sessions',
  'users',
  'credits',
  'library',
  'projects',
  'moderation',
  'pricing',
  'economics',
  'workflows',
  'agent',
  'skills',
  'showcase',
  'endpoints',
  'roles',
  'audit',
  'settings',
];

test('the console: its sign-in, every section, a drawer of a person and the search', async ({ page }) => {
  const problems: string[] = [];
  await page.goto(`${CONSOLE}/signin`);
  await settled(page);
  problems.push(...(await axe(page, 'console sign-in')));
  for (const section of SECTIONS) {
    await openConsole(page, section);
    problems.push(...(await axe(page, `console ${section}`)));
  }
  await openConsole(page, 'users');
  await page.getByRole('main').getByText('e2e-user@local.test').click();
  await expect(page.getByRole('dialog', { name: 'User' })).toBeVisible();
  await settled(page);
  problems.push(...(await axe(page, 'console, a drawer of a person')));
  await page.keyboard.press('Control+k');
  await expect(page.getByRole('dialog', { name: 'Search' })).toBeVisible();
  problems.push(...(await axe(page, 'console search')));
  expect(problems).toEqual([]);
});
