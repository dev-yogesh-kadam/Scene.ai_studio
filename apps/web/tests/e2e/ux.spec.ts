// What a new account is shown first (U6), the canvas's keyboard (U1) and the live region that says what happened (U2).

import { expect, test, type Page } from '@playwright/test';
import { axe } from './axe';
import { seedCanvas, type Seeded } from './seed';
import { done, makeImage, signIn } from './signin';
import { watch } from './watch';

let seeded: Seeded;
test.beforeAll(async ({ browser }) => {
  const page = await browser.newPage();
  await signIn(page);
  seeded = await seedCanvas(page, 'Canvas test');
  await page.close();
});

/** A new account, signed in on this page: it has made nothing and seen no tip. */
async function newcomer(page: Page) {
  const account = { email: `new-${Date.now()}@local.test`, name: 'New person', password: 'New-person-2026-pass' };
  const made = await page.request.post('/api/auth/register', { data: account });
  expect(made.ok(), await made.text()).toBe(true);
}

test('a new account sees three priced starters on Home, and a tip the first time the canvas opens', async ({
  page,
}) => {
  const problems = watch(page);
  await newcomer(page);
  await page.goto('/home');
  const starters = page.getByRole('region', { name: 'New here? Start from one of these' });
  await expect(starters.getByRole('button')).toHaveCount(3);
  await expect(starters.getByRole('button').first()).toContainText(/\d+ credits?/);
  await starters.getByRole('button', { name: /A product shot/ }).click();
  await expect(page.getByRole('textbox', { name: 'Prompt' })).toHaveValue(/glass perfume bottle/);

  await page.goto('/canvas');
  const tip = page.getByRole('complementary', { name: 'Tip' });
  await expect(tip).toBeVisible({ timeout: 15_000 });
  await tip.getByRole('button', { name: 'Got it' }).click();
  await expect(tip).toBeHidden();
  await expect
    .poll(async () => ((await (await page.request.get('/api/preferences')).json()) as { seen: string[] }).seen)
    .toContain('canvas-tip');
  await page.reload();
  await expect(page.getByRole('complementary', { name: 'Make something' })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole('complementary', { name: 'Tip' })).toHaveCount(0); // once only, on any computer
  expect(problems).toEqual([]);
});

test('the canvas keyboard: ? lists the keys, Delete asks and then deletes the selected frame', async ({ page }) => {
  await signIn(page);
  const job = await makeImage(page, { name: 'Key test', project_id: seeded.id });
  await done(page, job.id);
  await page.goto(`/canvas/${seeded.ref}`);
  await expect(page.getByText('5 items')).toBeVisible({ timeout: 15_000 });

  await page.keyboard.press('?');
  const sheet = page.getByRole('dialog', { name: 'Keyboard shortcuts' });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByText('Delete the selected frames (asks first)')).toBeVisible();
  expect(await axe(page, 'the keyboard sheet')).toEqual([]);
  await sheet.getByRole('button', { name: 'Done' }).click();

  await page.getByTitle('Key test', { exact: true }).first().click();
  await page.keyboard.press('Delete');
  const question = page.getByRole('dialog', { name: 'Delete "Key test"?' });
  await expect(question).toBeVisible();
  await question.getByRole('button', { name: 'Cancel' }).click();
  await expect(page.getByText('5 items')).toBeVisible(); // nothing deleted without a yes
  await page.getByTitle('Key test', { exact: true }).first().click();
  await page.keyboard.press('Delete');
  await page.getByRole('dialog', { name: 'Delete "Key test"?' }).getByRole('button', { name: 'Delete' }).click();
  await expect(page.getByText('4 items')).toBeVisible();
});

test('the live region says a picture is ready', async ({ page }) => {
  await signIn(page);
  await page.goto('/projects');
  const said = page.locator('[aria-live="polite"]').filter({ hasText: /ready/ });
  const job = await makeImage(page, { name: 'Announced' });
  await done(page, job.id);
  await expect(said).toHaveText('Image ready: Announced', { timeout: 15_000 });
});
