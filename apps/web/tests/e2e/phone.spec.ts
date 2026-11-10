// The phone site (apps/mobile, built to apps/mobile/dist and served by the studio at /m/): it opens and draws under the
// studio's Content-Security-Policy (no inline style: its libraries' CSS goes through apps/mobile/src/lib/cspStyles.ts)
// with nothing blocked and no error, and someone signs in on it.

import { devices, expect, test, type Page } from '@playwright/test';
import { ACCOUNTS } from './accounts';
import { axe } from './axe';
import { seedCanvas } from './seed';
import { done, makeImage, signIn } from './signin';
import { watch } from './watch';

test.use({ viewport: devices['iPhone 13'].viewport, userAgent: devices['iPhone 13'].userAgent, hasTouch: true });

// Home with something on it, whatever ran before: the user's own project with pictures (covers, latest work), and a
// project the admin shares with them (its card shows the owner's badge).
test.beforeAll(async ({ browser }) => {
  const page = await browser.newPage();
  await signIn(page);
  await seedCanvas(page, 'Canvas test');
  await signIn(page, 'admin');
  const known = (await (await page.request.get('/api/projects')).json()) as { projects: { name: string }[] };
  if (!known.projects.some((p) => p.name === 'Shared with the phone')) {
    const made = await page.request.post('/api/projects', { data: { name: 'Shared with the phone' } });
    const place = (await made.json()) as { id: number };
    await done(page, (await makeImage(page, { name: 'Their shot', project_id: place.id })).id);
    const shared = await page.request.post(`/api/projects/${place.id}/members`, {
      data: { people: [{ email: ACCOUNTS.user.email, role: 'viewer' }] },
    });
    expect(shared.ok()).toBe(true);
  }
  await page.close();
});

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
  expect(await axe(page, 'phone sign-in')).toEqual([]);
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
  await expect(page.getByText('Shared with the phone').first()).toBeVisible({ timeout: 15_000 });
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(600);
  await styled(page);
  expect(problems).toEqual([]);
  expect(await axe(page, 'phone home')).toEqual([]);
});
