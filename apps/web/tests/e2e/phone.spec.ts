// The phone site (apps/mobile, built to apps/mobile/dist and served by the studio at /m/): it opens and draws under the
// studio's Content-Security-Policy (no inline style: its libraries' CSS goes through apps/mobile/src/lib/cspStyles.ts)
// with nothing blocked and no error, and someone signs in on it.

import { devices, expect, test, type Page } from '@playwright/test';
import { ACCOUNTS } from './accounts';
import { watch } from './watch';

test.use({ viewport: devices['iPhone 13'].viewport, userAgent: devices['iPhone 13'].userAgent, hasTouch: true });

/** The site's CSS applies: the page's own file (reset.css), and the libraries' rules in adopted sheets. */
async function styled(page: Page) {
  await expect(page.locator('#root')).toHaveCSS('display', 'flex'); // reset.css
  const rules = await page.evaluate(() => document.adoptedStyleSheets.reduce((n, s) => n + s.cssRules.length, 0));
  expect(rules).toBeGreaterThan(100); // React Native Web's classes, Reanimated's keyframes, the fonts
  expect(await page.evaluate(() => document.querySelectorAll('style').length)).toBe(0); // no inline <style> in the page
}

test('the phone site loads at /m/ and draws, with no policy violation or error', async ({ page }) => {
  const problems = watch(page);
  const answer = await page.goto('/m/');
  expect(answer?.status()).toBe(200);
  const policy = answer?.headers()['content-security-policy'] ?? '';
  expect(policy).toContain("script-src 'self'");
  expect(policy).toContain("style-src 'self';");
  await expect(page.getByPlaceholder('Email')).toBeVisible();
  await page.waitForLoadState('networkidle');
  await styled(page);
  expect(await page.evaluate(() => [...document.fonts].filter((f) => f.status === 'loaded').length)).toBeGreaterThan(0);
  expect(problems).toEqual([]);
});

test('a phone opening a studio page is sent to the phone site, and signs in there', async ({ page }) => {
  const problems = watch(page);
  await page.goto('/projects');
  await expect(page).toHaveURL(/\/m\//);
  const { email, password } = ACCOUNTS.user;
  await page.getByPlaceholder('Email').fill(email);
  await page.getByPlaceholder('Password').fill(password);
  await page.getByText('Sign In', { exact: true }).click();
  await expect(page.getByPlaceholder('Email')).toBeHidden({ timeout: 15_000 });
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(600);
  await styled(page);
  expect(problems).toEqual([]);
});
