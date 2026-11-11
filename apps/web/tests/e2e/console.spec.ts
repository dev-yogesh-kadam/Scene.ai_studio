// The admin console in the React build, on its own port: its sign-in, every section at its own address, and a person
// who is not an admin kept out.

import { expect, test } from '@playwright/test';
import { CONSOLE } from '../../playwright.config';
import { ACCOUNTS } from './accounts';
import { watch } from './watch';

const SECTIONS: [string, string][] = [
  ['overview', 'Overview'],
  ['jobs', 'Jobs'],
  ['system', 'System'],
  ['sessions', 'Sessions'],
  ['users', 'Users'],
  ['credits', 'Credits'],
  ['library', 'Library'],
  ['projects', 'Projects'],
  ['moderation', 'Moderation'],
  ['pricing', 'Pricing'],
  ['economics', 'Economics'],
  ['workflows', 'Workflows'],
  ['agent', 'Agent'],
  ['skills', 'Skills'],
  ['showcase', 'Home page'],
  ['endpoints', 'Servers'],
  ['roles', 'Roles'],
  ['audit', 'Audit log'],
  ['settings', 'Settings'],
];

async function signIn(page: import('@playwright/test').Page, who: keyof typeof ACCOUNTS) {
  await page.getByPlaceholder('you@company.com').fill(ACCOUNTS[who].email);
  await page.getByPlaceholder('Your password').fill(ACCOUNTS[who].password);
  await page.getByRole('region', { name: 'Sign-in form' }).getByRole('button', { name: 'Sign in' }).click();
}

test('an admin signs in, lands on the section asked for, and every section opens at its address', async ({ page }) => {
  const problems = watch(page);
  await page.goto(`${CONSOLE}/users`);
  await expect(page).toHaveURL(/\/signin$/);
  await expect(page.getByRole('heading', { name: 'Admin sign-in' })).toBeVisible();
  await signIn(page, 'admin');
  await expect(page).toHaveURL(/\/users$/); // where it was opened before signing in
  await expect(page.getByRole('heading', { name: 'Users', level: 1 })).toBeVisible();
  await expect(page.getByTitle('People with the studio open right now. Several tabs count once.')).toBeVisible();

  for (const [id, label] of SECTIONS) {
    // a link's name may end in its count: System's open alerts (the test studio's Claude connection has no key), Jobs' queue
    const link = new RegExp(`^${label}(\\s|$)`);
    await page.getByRole('navigation', { name: 'Sections' }).getByRole('link', { name: link }).click();
    await expect(page).toHaveURL(new RegExp(`/${id}$`));
    await expect(page.getByRole('heading', { name: label, level: 1 })).toBeVisible();
    await expect(page.locator('main.view .error')).toHaveCount(0);
  }
  await page.goto(`${CONSOLE}/audit`); // an address opened straight away
  await expect(page.getByRole('heading', { name: 'Audit log', level: 1 })).toBeVisible();
  expect(problems.filter((p) => !p.includes('/api/console/me'))).toEqual([]);

  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page.getByRole('heading', { name: 'Admin sign-in' })).toBeVisible();
});

test('a person who is not an admin is kept out of the console', async ({ page }) => {
  await page.goto(`${CONSOLE}/signin`);
  await signIn(page, 'user');
  await expect(page.getByRole('region', { name: 'Sign-in form' }).locator('.notice')).toHaveText(
    'This account is not an admin.',
  );
});
