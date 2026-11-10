// The React build loads under the studio's Content-Security-Policy, on both ports, with nothing blocked.

import { expect, test } from '@playwright/test';
import { CONSOLE } from '../../playwright.config';
import { watch } from './watch';

test('the studio page loads with no policy violations or errors', async ({ page }) => {
  const problems = watch(page);
  const answer = await page.goto('/signin');
  expect(answer?.headers()['content-security-policy']).toContain("script-src 'self'");
  await expect(page.locator('#app')).not.toBeEmpty();
  expect(problems).toEqual([]);
});

test('the console page loads on its own port with no policy violations or errors', async ({ page }) => {
  const problems = watch(page);
  await page.goto(`${CONSOLE}/signin`);
  await expect(page.locator('#app')).not.toBeEmpty();
  expect(problems).toEqual([]);
});
