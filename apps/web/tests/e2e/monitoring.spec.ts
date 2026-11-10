// What goes wrong in a page reaches the studio (R2, T5): an uncaught error and an unhandled rejection, with their page
// and build, and the Web Vitals of a page that is measured; the console's System section shows them.

import { expect, test, type Page } from '@playwright/test';
import { CONSOLE } from '../../playwright.config';
import { ACCOUNTS } from './accounts';
import { signIn } from './signin';

type Seen = {
  errors: { kind: string; message: string; page: string; build: string; email: string }[];
  vitals: { name: string; count: number }[];
};

async function asAdmin(page: Page) {
  const { email, password } = ACCOUNTS.admin;
  const answer = await page.request.post(CONSOLE + '/api/console/login', { data: { email, password } });
  expect(answer.ok()).toBe(true);
  return async () => (await (await page.request.get(CONSOLE + '/api/admin/client-errors')).json()) as Seen;
}

test('an uncaught error and an unhandled rejection are told to the studio, and the console shows them', async ({
  page,
}) => {
  await signIn(page);
  await page.goto('/library');
  await expect(page.getByRole('heading', { name: 'Library' })).toBeVisible();
  await page.evaluate(() => {
    setTimeout(() => {
      throw new Error('e2e: a thrown error');
    });
    void Promise.reject(new Error('e2e: a rejected promise'));
  });
  const seen = await asAdmin(page);
  await expect
    .poll(async () =>
      (await seen()).errors
        .filter((e) => e.message.startsWith('e2e:'))
        .map((e) => e.kind)
        .sort(),
    )
    .toEqual(['error', 'rejection']);
  const thrown = (await seen()).errors.find((e) => e.message === 'e2e: a thrown error')!;
  expect(thrown.page).toBe('/library');
  expect(thrown.build).toMatch(/^studio-.+\.js$/); // the entry file, named by its content
  expect(thrown.email).toBe(ACCOUNTS.user.email);

  await page.goto(`${CONSOLE}/system`);
  const card = page.getByRole('heading', { name: 'In the browser' }).locator('xpath=../..');
  await expect(card.getByText('e2e: a thrown error')).toBeVisible();
  await expect(card.getByText('Unhandled: e2e: a rejected promise')).toBeVisible();
});

test('a measured page sends its Web Vitals when it is left', async ({ page }) => {
  await page.addInitScript(() => {
    Math.random = () => 0; // this page is one of the tenth that are measured
  });
  await signIn(page);
  const seen = await asAdmin(page);
  const measured = async () => (await seen()).vitals.reduce((n, v) => n + v.count, 0);
  const before = await measured();
  await page.goto('/home');
  await expect(page.getByRole('heading', { name: 'What are you making today?' })).toBeVisible();
  await page.mouse.click(5, 300); // an interaction: INP has one, and LCP is final from here
  await page.waitForTimeout(500);
  // the tab is put away (another tab chosen): the page is hidden and says its numbers
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  // what Chrome measured of LCP, INP and CLS (a headless browser may not give an LCP for a page of text)
  await expect.poll(measured).toBeGreaterThan(before);
});
