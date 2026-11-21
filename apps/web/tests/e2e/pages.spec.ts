// The studio's pages in the React build, each with its main action, against the studio's own backend and the fake v1
// provider.

import { expect, test } from '@playwright/test';
import { ACCOUNTS } from './accounts';
import { done, makeImage, signIn } from './signin';
import { watch } from './watch';

test.describe.configure({ mode: 'serial' });

test('the landing page draws its monitor, and a prompt there waits for after signing in', async ({ page }) => {
  const problems = watch(page);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Direct your scene.' })).toBeVisible();
  await expect(page.getByTestId('set-plane').first()).toBeAttached(); // the drawn set, plane by plane
  await expect(page.getByText('Most AI video tools give you a slot machine.')).toBeAttached(); // the sections below
  await page.getByPlaceholder('A girl in a yellow raincoat on a rainy street at night').fill('A lighthouse at dawn');
  await page.getByRole('button', { name: 'Make this' }).click();
  // the prompt travels in the address, to the sign-in form and on to Home's prompt box
  await expect(page).toHaveURL(/\/signup\?prompt=A\+lighthouse\+at\+dawn$/);
  await page.goto('/signin?prompt=A+lighthouse+at+dawn');
  await page.getByPlaceholder('you@company.com').fill(ACCOUNTS.user.email);
  await page.getByPlaceholder('Your password').fill(ACCOUNTS.user.password);
  await page.getByRole('region', { name: 'Sign-in form' }).getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/home\?prompt=A\+lighthouse\+at\+dawn$/);
  await expect(page.getByRole('textbox', { name: 'Prompt' })).toHaveValue('A lighthouse at dawn');
  expect(await page.evaluate(() => localStorage.getItem('scene.firstPrompt'))).toBeNull();
  expect(problems).toEqual([]);
});

test("Create's hand-offs come in the address: Re-run loads an item's settings, and a reload keeps them", async ({
  page,
}) => {
  await signIn(page);
  // made with a prompt of its own, in the first image workflow's prompt box
  const workflows = (await (await page.request.get('/api/workflows')).json()) as {
    workflows: { id: string; kind: string }[];
  };
  const workflow = workflows.workflows.find((w) => w.kind === 'image')!.id;
  const form = (await (await page.request.get('/api/workflows/' + workflow)).json()) as {
    controls: { id: string; role?: string }[];
  };
  const promptBox = form.controls.find((c) => c.role === 'prompt')!.id;
  const job = await makeImage(page, { name: 'Handed over', values: { [promptBox]: 'A heron in the reeds' } });
  await done(page, job.id);
  const item = (
    (await (await page.request.get('/api/library?job=' + job.id + '&limit=1')).json()) as { items: { id: number }[] }
  ).items[0];
  await page.goto('/library');
  await page.getByRole('button', { name: 'More for Handed over' }).click();
  await page.getByRole('menuitem', { name: 'Re-run with the same settings' }).click();
  await expect(page).toHaveURL(new RegExp(`/create\\?rerun=${item.id}$`));
  await expect(page.locator('textarea').first()).toHaveValue('A heron in the reeds');
  await page.goto(`/create?rerun=${item.id}&from=canvas`);
  await expect(page.getByRole('link', { name: '← Canvas' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('link', { name: '← Canvas' })).toBeVisible();
  await expect(page.locator('textarea').first()).toHaveValue('A heron in the reeds');
});

test('Settings changes the password, and back', async ({ page }) => {
  await signIn(page);
  await page.goto('/settings');
  const change = async (from: string, to: string) => {
    await page.locator('input[name=current]').fill(from);
    await page.locator('input[name=new]').fill(to);
    const [answer] = await Promise.all([
      page.waitForResponse((r) => r.url().endsWith('/api/auth/password')),
      page.getByRole('button', { name: 'Change password' }).click(),
    ]);
    expect(answer.status()).toBe(200);
    await expect(page.locator('.notice.ok')).toHaveText('Password changed. Other devices were signed out.');
  };
  await change(ACCOUNTS.user.password, 'A-new-password-2026');
  await change('A-new-password-2026', ACCOUNTS.user.password);
  await expect(page.getByRole('heading', { name: 'Two-step sign-in' })).toBeVisible();
  await expect(page.getByText('Off. Turn it on')).toBeVisible();
});

test('the Guide marks the section in view', async ({ page }) => {
  await signIn(page);
  await page.goto('/guide');
  await page.getByRole('navigation', { name: 'Contents' }).getByRole('link', { name: 'Credits' }).click();
  await expect(page.getByRole('navigation', { name: 'Contents' }).getByRole('link', { name: 'Credits' })).toHaveClass(
    /on/,
  );
});

test('Skills lists the recipes', async ({ page }) => {
  await signIn(page);
  await page.goto('/skills');
  await expect(page.getByRole('heading', { name: 'Skills' })).toBeVisible();
  await expect(page.getByText('Recipes the agent follows for a kind of work.')).toBeVisible();
});

test('a project: made, opened, a module added, analytics, deleted', async ({ page }) => {
  const problems = watch(page);
  await signIn(page);
  await page.goto('/projects');
  await page
    .getByRole('button', { name: /New project|Create your first project/ })
    .first()
    .click();
  await page.getByRole('dialog').getByRole('textbox').first().fill('E2E film');
  await page.getByRole('button', { name: 'Create project' }).click();
  await expect(page).toHaveURL(/\/project\/PRJ/);
  await expect(page.getByRole('heading', { name: 'E2E film' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Where you are' })).toContainText('E2E film');

  await page.getByRole('button', { name: 'Add module' }).click();
  await page.getByRole('button', { name: 'Create module' }).click();
  await expect(page).toHaveURL(/\/canvas\/PRJ\w+\/module\/MOD/);

  await page.goBack();
  await page.getByRole('link', { name: /View analytics/ }).click();
  await expect(page.getByRole('heading', { name: 'Analytics' })).toBeVisible();
  await expect(page.getByText('Project spend')).toBeVisible();
  await page.getByRole('button', { name: 'Last 30 days' }).click();
  await page.getByRole('link', { name: 'Back to project' }).click();

  await page.getByRole('button', { name: 'Delete project' }).click();
  await page
    .getByRole('dialog', { name: 'Delete "E2E film"?' })
    .getByRole('button', { name: 'Delete project' })
    .click();
  await expect(page).toHaveURL(/\/projects$/);
  expect(problems).toEqual([]);
});

test('Create: a picture from a prompt, queued, made, shown under Latest', async ({ page }) => {
  const problems = watch(page);
  await signIn(page);
  await page.goto('/create');
  await page.getByRole('button', { name: 'Image', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Workflow' })).toBeVisible();
  await page.locator('.field textarea').first().fill('A red kite over green hills');
  await expect(page.locator('.btn.generate .cost')).toContainText('credit');
  await page.locator('.btn.generate').click();
  const job = page.getByRole('list', { name: 'Jobs' }).getByRole('listitem').first();
  await expect(job).toBeVisible();
  await expect(job.getByText('Done', { exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('article').first()).toBeVisible({ timeout: 15_000 });
  expect(problems).toEqual([]);
});

test('Library: the picture is there, opens in the viewer, and is deleted', async ({ page }) => {
  await signIn(page);
  const job = await makeImage(page, { name: 'Library test' });
  await done(page, job.id);
  await page.goto('/library');
  const card = page.getByRole('article', { name: 'Library test' }).first();
  await expect(card).toBeVisible();
  await card.locator('[data-picture]').click();
  const viewer = page.getByRole('dialog', { name: 'Viewer' });
  await expect(viewer).toBeVisible();
  await expect(viewer.getByRole('heading', { level: 2 })).toHaveText('Library test');
  await page.keyboard.press('Escape');
  await expect(viewer).toHaveCount(0);
  await card.hover();
  await card.getByRole('button', { name: 'More for Library test' }).click();
  await page.getByRole('menuitem', { name: 'Delete' }).click();
  await page.getByRole('dialog', { name: 'Delete "Library test"?' }).getByRole('button', { name: 'Delete' }).click();
  await expect(page.getByRole('article', { name: 'Library test' })).toHaveCount(0);
});

test('Home: the composer queues a job', async ({ page }) => {
  await signIn(page);
  await page.goto('/home');
  await expect(page.getByRole('heading', { name: 'What are you making today?' })).toBeVisible();
  await page.getByLabel('Prompt').fill('A paper boat in a puddle');
  const composer = page.getByRole('group', { name: 'Composer' });
  const workflow = composer.getByRole('combobox').first();
  const image = await workflow
    .locator('option', { hasText: /^Image · / })
    .first()
    .getAttribute('value');
  await workflow.selectOption(image!);
  await composer.locator('.btn.generate').click();
  await expect(page.getByText('Added to the queue.')).toBeVisible();
});
