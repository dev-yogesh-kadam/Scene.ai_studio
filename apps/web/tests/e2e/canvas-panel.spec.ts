// How the canvas's side panel behaves (written against the build before the panel became React components, and kept
// for the rewrite): its tabs, closing and Ctrl+J, the remembered tab, Quick actions making a picture, "+" on a frame,
// the NeuralCore tab, and Bulk generation for an admin only.

import { expect, test, type Page } from '@playwright/test';
import { seedCanvas, type Seeded } from './seed';
import { signIn } from './signin';
import { watch } from './watch';

let seeded: Seeded;

async function openCanvas(page: Page) {
  await page.goto(`/canvas/${seeded.ref}`);
  await expect(page.getByText(/^\d+ items$/)).toBeVisible({ timeout: 15_000 });
}

const panelTitle = (page: Page) => page.getByRole('complementary', { name: 'Make something' }).locator('b').first();

test.beforeAll(async ({ browser }) => {
  const page = await browser.newPage();
  await signIn(page);
  seeded = await seedCanvas(page, 'Panel test');
  await page.close();
});

test.beforeEach(async ({ page }) => {
  await signIn(page);
  await page.addInitScript(() => {
    if (!sessionStorage.getItem('tab-set')) {
      localStorage.setItem('scene.panel.tab', 'quick');
      sessionStorage.setItem('tab-set', '1');
    }
  });
});

test('the panel opens on Quick actions, switches tabs, closes, and Ctrl+J brings it back', async ({ page }) => {
  const problems = watch(page);
  await openCanvas(page);
  const panel = page.getByRole('complementary', { name: 'Make something' });
  await expect(panel).toBeVisible();
  await expect(panelTitle(page)).toHaveText('Quick actions');
  await expect(panel.getByRole('button', { name: 'Generate image' })).toBeVisible();
  await expect(panel.getByRole('button', { name: 'Bulk generation' })).toHaveCount(0); // an admin's tool

  await panel.getByRole('button', { name: 'NeuralCore' }).click();
  await expect(panelTitle(page)).toHaveText('NeuralCore');
  await panel.getByRole('button', { name: 'Agent' }).click();
  await expect(panelTitle(page)).toHaveText('Agent');

  await panel.getByRole('button', { name: 'Close the panel' }).click();
  await expect(page.getByRole('button', { name: 'Panel', exact: true })).toHaveAttribute('aria-pressed', 'false');
  await page.locator('body').press('Control+j');
  await expect(page.getByRole('button', { name: 'Panel', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(panelTitle(page)).toHaveText('Agent');

  // the tab is remembered
  await page.reload();
  await expect(panelTitle(page)).toHaveText('Agent', { timeout: 15_000 });
  expect(problems.filter((p) => !p.includes('/api/agent/status'))).toEqual([]);
});

test('the panel is wider when its edge is dragged, and the usual width again on a double click', async ({ page }) => {
  await openCanvas(page);
  const panel = page.getByRole('complementary', { name: 'Make something' });
  const grip = panel.getByRole('separator');
  const before = (await panel.boundingBox())!.width;
  const at = (await grip.boundingBox())!;
  await page.mouse.move(at.x + at.width / 2, at.y + 200);
  await page.mouse.down();
  await page.mouse.move(at.x + at.width / 2 - 60, at.y + 200, { steps: 5 });
  await page.mouse.up();
  await expect.poll(async () => Math.round((await panel.boundingBox())!.width)).toBe(Math.round(before + 60));
  expect(await page.evaluate(() => localStorage.getItem('scene.panel.width'))).toBe(String(Math.round(before + 60)));
  await grip.dblclick();
  await expect.poll(async () => Math.round((await panel.boundingBox())!.width)).toBe(Math.round(before));
});

test('Quick actions: Generate image makes a picture that lands on the canvas', async ({ page }) => {
  await openCanvas(page);
  const before = Number((await page.getByText(/^\d+ items$/).textContent())!.split(' ')[0]);
  const panel = page.getByRole('complementary', { name: 'Make something' });
  await panel.getByRole('button', { name: 'Generate image' }).click();
  const model = panel.getByRole('combobox', { name: 'Model' });
  await expect(model).toBeVisible();
  // nothing is chosen for a user who never chose (no default model): they pick one, here the first model offered
  const first = await model.locator('option:not([disabled])').first().getAttribute('value');
  await model.selectOption(first!);
  await panel.getByRole('textbox', { name: 'Prompt' }).fill('A lighthouse at dusk');
  const generate = panel.getByTitle('Generate (Ctrl or ⌘ + Enter)');
  await expect(generate).toBeEnabled();
  await expect(generate).toContainText(/\d+ cr/);
  await generate.click();
  await expect(page.getByText(`${before + 1} items`)).toBeVisible({ timeout: 30_000 });
  await panel.getByRole('button', { name: 'Back to quick actions' }).click();
  await expect(panel.getByRole('button', { name: 'Generate video' })).toBeVisible();
});

test('"+" on a frame puts it into the agent\'s message, opening the agent', async ({ page }) => {
  await openCanvas(page);
  await page.getByRole('button', { name: 'Add Second to the chat' }).click({ force: true });
  await expect(panelTitle(page)).toHaveText('Agent');
  const panel = page.getByRole('complementary', { name: 'Make something' });
  await expect(panel.getByText('Second', { exact: true }).first()).toBeVisible();
});

test('NeuralCore: the cast lists its entries, and a script is added from Add', async ({ page }) => {
  await openCanvas(page);
  const panel = page.getByRole('complementary', { name: 'Make something' });
  await panel.getByRole('button', { name: 'NeuralCore' }).click();
  await expect(panel.getByText('This module', { exact: true })).toBeVisible();
  await expect(panel.getByRole('textbox', { name: 'Name' }).first()).toHaveValue('Meera');
  await panel.getByRole('button', { name: 'Add', exact: true }).click();
  await page.getByText('Paste a script').click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('heading')).toHaveText('Add a script to the NeuralCore');
  await dialog.getByRole('textbox').first().fill('Ep 1');
  await dialog.getByPlaceholder('Paste the script here.').fill('INT. KITCHEN - NIGHT');
  await dialog.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(panel.locator('input[aria-label="Name"]')).toHaveCount(2);
  await expect(panel.getByRole('textbox', { name: 'Name' }).nth(1)).toHaveValue('Ep 1');

  // You: what the agent remembers of this user
  await panel.getByRole('button', { name: 'You', exact: true }).click();
  await expect(panel.getByText(/What the agent remembers of you/)).toBeVisible();
});

test('Bulk generation is an admin tab that opens the compare board', async ({ page }) => {
  await signIn(page, 'admin');
  const place = await seedCanvas(page, 'Bulk test');
  await page.goto(`/canvas/${place.ref}`);
  const panel = page.getByRole('complementary', { name: 'Make something' });
  await panel.getByRole('button', { name: 'Bulk generation' }).click();
  await expect(panelTitle(page)).toHaveText('Bulk generation');
  await panel.getByRole('button', { name: 'Open the compare board' }).click();
  const board = page.getByRole('dialog', { name: 'Compare board' });
  await expect(board).toBeVisible();
  await expect(board.getByText('Set up a test on the left')).toBeVisible();
  await expect(board.getByRole('button', { name: 'Run the test · 0 renders' })).toBeDisabled();
  await board.getByPlaceholder('What to make').fill('A red kite');
  await board.getByRole('button', { name: 'All', exact: true }).click();
  await expect(board.getByRole('button', { name: /^Run the test · \d+ renders?$/ })).toBeEnabled();
  await page.keyboard.press('Escape');
  await expect(board).toBeHidden();
});
