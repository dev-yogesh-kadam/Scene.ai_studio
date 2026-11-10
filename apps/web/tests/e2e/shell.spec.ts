// Signing in through the form, the shell around every page, and signing out, in the React studio.

import { expect, test } from '@playwright/test';
import { ACCOUNTS } from './accounts';
import { watch } from './watch';

test('sign in, see the shell, sign out', async ({ page }) => {
  const problems = watch(page);
  await page.goto('/library'); // any page of the studio asks someone signed out to sign in
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  await expect(page.getByTestId('scene').locator('svg')).toBeVisible(); // the scene is drawn
  await expect(page.getByTestId('timecode')).not.toHaveText('01:00:00:00'); // and its timecode runs

  await page.getByPlaceholder('you@company.com').fill(ACCOUNTS.user.email);
  await page.getByPlaceholder('Your password').fill(ACCOUNTS.user.password);
  await page.getByRole('region', { name: 'Sign-in form' }).getByRole('button', { name: 'Sign in' }).click();

  await expect(page).toHaveURL(/\/projects$/);
  const sidebar = page.getByRole('complementary', { name: 'Scene.ai' });
  await expect(sidebar.getByRole('link', { name: 'All projects' })).toHaveClass(/on/);
  const me = (await (await page.request.get('/api/auth/me')).json()) as { credits: number };
  await expect(page.getByTitle('Credits pay for generations. An admin can add more.')).toContainText(
    me.credits.toLocaleString('en-US'),
  );
  await expect(page).toHaveTitle('All projects · Scene.ai');

  // A page without the sidebar has the pages in the dropdown under the logo
  await page.goto('/settings');
  await expect(page.locator('[data-layout]')).toHaveAttribute('data-layout', 'compact');
  await page.getByRole('button', { name: 'Open the menu' }).click();
  await expect(page.getByRole('menu', { name: 'Pages' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('menu', { name: 'Pages' })).toBeHidden();

  await page.getByRole('button', { name: 'Your account' }).click();
  await page.getByRole('menuitem', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/$/); // signed out: the landing page
  await expect(page.getByRole('heading', { name: 'Direct your scene.' })).toBeVisible();
  expect(problems).toEqual([]);
});

test('a wrong password is said so on the form', async ({ page }) => {
  await page.goto('/signin');
  await page.getByPlaceholder('you@company.com').fill(ACCOUNTS.user.email);
  await page.getByPlaceholder('Your password').fill('not the password');
  await page.getByRole('region', { name: 'Sign-in form' }).getByRole('button', { name: 'Sign in' }).click();
  await expect(page.locator('.notice')).toHaveText('Wrong email or password.');
});
