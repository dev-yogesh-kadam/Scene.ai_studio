// How the canvas's board behaves (written against the build before the canvas became React components, and kept for
// the rewrite): the shots as rows, a stack of takes, selecting, the viewer, the camera keys, naming a shot, the
// NeuralCore boards, the tools on the left, and a frame for work in progress.

import { expect, test, type Page } from '@playwright/test';
import { canvasBoard, seedCanvas, type Seeded } from './seed';
import { signIn } from './signin';
import { watch } from './watch';

let seeded: Seeded;

async function openCanvas(page: Page) {
  await page.goto(`/canvas/${seeded.ref}`);
  await expect(page.getByText('4 items')).toBeVisible({ timeout: 15_000 });
}

const frame = (page: Page, name: string) => page.getByTitle(name, { exact: true });

test.beforeAll(async ({ browser }) => {
  const page = await browser.newPage();
  await signIn(page);
  seeded = await seedCanvas(page, 'Board test');
  await page.close();
});

test.beforeEach(async ({ page }) => {
  await signIn(page);
});

test('the shots are rows named down the left, a numbered shot first, its takes one stack', async ({ page }) => {
  const problems = watch(page);
  await openCanvas(page);
  await expect(page.getByRole('button', { name: 'Shot 1', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Shot 2', exact: true })).toBeVisible();
  await expect(frame(page, 'Second')).toBeVisible();
  await expect(frame(page, 'Take B')).toBeVisible(); // the newest take is on top
  await expect(page.getByTitle('Take A: an earlier take. Click to put it on top.')).toBeAttached();
  const takes = page.getByRole('group', { name: 'Takes of this shot' });
  await expect(takes).toContainText('2 / 2');

  // The earlier take goes on top, and stays there: the choice is saved with the layout.
  await takes.getByRole('button', { name: 'The earlier take' }).click();
  await expect(page.getByRole('group', { name: 'Takes of this shot' })).toContainText('1 / 2');
  await expect
    .poll(async () => (await canvasBoard(page, seeded.id)).picks?.['shot:1']?.key)
    .toBe(seeded.items['Take A']);
  await page.reload();
  await expect(page.getByRole('group', { name: 'Takes of this shot' })).toContainText('1 / 2', { timeout: 15_000 });
  await page.getByRole('group', { name: 'Takes of this shot' }).getByRole('button', { name: 'The later take' }).click();
  await expect(page.getByRole('group', { name: 'Takes of this shot' })).toContainText('2 / 2');
  await expect
    .poll(async () => (await canvasBoard(page, seeded.id)).picks?.['shot:1']?.key)
    .toBe(seeded.items['Take B']);

  // The saved layout keeps its shape: rows of keys, a count, the picks.
  const board = await canvasBoard(page, seeded.id);
  expect(board.rows!.map((r) => [r.shot ?? null, r.keys.length])).toEqual([
    [1, 2],
    [null, 1],
  ]);
  expect(typeof board.count).toBe('number');
  expect(problems).toEqual([]);
});

test('a NeuralCore entry made from a picture sits on its board, not in a shot', async ({ page }) => {
  await openCanvas(page);
  await expect(page.getByText(/^Characters\s*1$/)).toBeVisible(); // the board's name and how many it holds
  await expect(page.getByTitle('Meera', { exact: true })).toBeVisible(); // the entry's name over its frame
  await expect(frame(page, 'First')).toBeVisible();
  const board = await canvasBoard(page, seeded.id);
  expect(board.rows!.flatMap((r) => r.keys)).not.toContain(seeded.items.First);
});

test('a click selects, the bar over the selection acts on it, Escape lets go', async ({ page }) => {
  await openCanvas(page);
  await frame(page, 'Second').click();
  await expect(page.getByRole('button', { name: 'Open', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Download', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Add to NeuralCore' })).toBeVisible();
  await frame(page, 'Take B').click({ modifiers: ['Shift'] });
  await expect(page.getByText('2 selected', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Download 2' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByText('2 selected', { exact: true })).toBeHidden();
  await expect(page.getByRole('button', { name: 'Download 2' })).toBeHidden();
});

test('Enter or a double click opens the viewer, with the takes of a stack under it', async ({ page }) => {
  await openCanvas(page);
  await frame(page, 'Second').click();
  await page.keyboard.press('Enter');
  const viewer = page.getByRole('dialog');
  await expect(viewer).toBeVisible();
  await expect(viewer).toContainText('Second');
  await page.keyboard.press('Escape');
  await expect(viewer).toBeHidden();
  await frame(page, 'Take B').dblclick();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByRole('dialog')).toContainText('Take 2 · In use');
  await page.keyboard.press('Escape');
});

test('0 zooms to 100%, 1 fits everything, and the zoom shows on the bar', async ({ page }) => {
  await openCanvas(page);
  const zoom = page.getByTitle('Zoom to 100% (0)');
  const fitted = await zoom.textContent();
  await page.keyboard.press('0');
  await expect(zoom).toHaveText('100%');
  await page.keyboard.press('1');
  await expect(zoom).toHaveText(fitted!);
  await page.getByRole('button', { name: 'Fit', exact: true }).click();
  await expect(zoom).toHaveText(fitted!);
});

test('a shot is named by clicking its name; the name is kept with the layout', async ({ page }) => {
  await openCanvas(page);
  await page.getByRole('button', { name: 'Shot 2', exact: true }).click();
  const box = page.getByRole('textbox', { name: 'Name of the shot' });
  await expect(box).toHaveValue('Shot 2');
  await box.fill('Opening');
  await box.press('Enter');
  await expect(page.getByRole('button', { name: 'Opening', exact: true })).toBeVisible();
  await expect.poll(async () => (await canvasBoard(page, seeded.id)).rows!.map((r) => r.name)).toContain('Opening');
  // Escape leaves it as it was
  await page.getByRole('button', { name: 'Opening', exact: true }).click();
  await page.getByRole('textbox', { name: 'Name of the shot' }).fill('Something else');
  await page.getByRole('textbox', { name: 'Name of the shot' }).press('Escape');
  await expect(page.getByRole('button', { name: 'Opening', exact: true })).toBeVisible();
  // and an empty name, or the usual one, gives the usual name back
  await page.getByRole('button', { name: 'Opening', exact: true }).click();
  await page.getByRole('textbox', { name: 'Name of the shot' }).fill('Shot 2');
  await page.getByRole('textbox', { name: 'Name of the shot' }).press('Enter');
  await expect.poll(async () => (await canvasBoard(page, seeded.id)).rows!.map((r) => r.name)).not.toContain('Opening');
});

test('the library drawer lists the work, by kind and by name, and closes', async ({ page }) => {
  await openCanvas(page);
  await page.getByRole('button', { name: 'Library' }).click();
  const drawer = page.getByRole('dialog', { name: 'Library' });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText('Second', { exact: true }).first()).toBeVisible();
  await expect(drawer.getByText('On this canvas').first()).toBeVisible();
  await drawer.getByRole('searchbox', { name: 'Search the library' }).fill('take');
  await expect(drawer.getByText('Second', { exact: true })).toBeHidden();
  await expect(drawer.getByText('Take A', { exact: true }).first()).toBeVisible();
  await drawer.getByRole('button', { name: 'Videos' }).click();
  await expect(drawer.getByText('Nothing matches.')).toBeVisible();
  await drawer.getByRole('button', { name: 'Close the library' }).click();
  await expect(drawer).toBeHidden();
});

test('a file uploaded from the tools lands on the canvas, selected', async ({ page }) => {
  await openCanvas(page);
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Upload an image, video or sound' }).click();
  const png = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
    'base64',
  );
  await (await chooser).setFiles({ name: 'Upload test.png', mimeType: 'image/png', buffer: png });
  await expect(page.getByRole('status')).toContainText('Uploaded. It is on the canvas.');
  await expect(page.getByText('5 items')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Open', exact: true })).toBeVisible(); // it is selected
  const library = (await (await page.request.get(`/api/library?project=${seeded.id}`)).json()) as {
    items: { id: number; name: string }[];
  };
  await page.request.delete(`/api/library/${library.items.find((i) => i.name.startsWith('Upload test'))!.id}`);
});

test('a frame dragged into the gap between two shots starts a new shot there', async ({ page }) => {
  await openCanvas(page);
  await page.keyboard.press('0');
  const second = (await frame(page, 'Second').boundingBox())!;
  const top = (await frame(page, 'Take B').boundingBox())!;
  await page.mouse.move(second.x + second.width / 2, second.y + 10);
  await page.mouse.down();
  const gapY = (top.y + top.height + second.y) / 2 + 6;
  for (let i = 1; i <= 10; i++)
    await page.mouse.move(second.x + second.width / 2, second.y + 10 + ((gapY - second.y - 10) * i) / 10);
  await expect(page.getByText('New shot here')).toBeVisible();
  for (let i = 1; i <= 4; i++) await page.mouse.move(second.x + second.width / 2, gapY - i * 6);
  await page.mouse.up();
  await expect(page.getByText('New shot here')).toBeHidden();
  // a numbered shot stays first, so the new shot keeps its place after it
  await expect
    .poll(async () => ((await canvasBoard(page, seeded.id)).rows ?? []).filter((r) => r.keys.length).length)
    .toBe(2);
});
