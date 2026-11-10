// End-to-end tests (Playwright, Chromium only) against a studio of their own: the React build served by this working
// tree's backend, a new database, and the fake ComfyUI. Build first: `npm run e2e` does both.

import { defineConfig } from '@playwright/test';

export const STUDIO = 'http://127.0.0.1:8281';
export const CONSOLE = 'http://127.0.0.1:8290';

export default defineConfig({
  testDir: 'tests/e2e',
  globalSetup: './tests/e2e/global-setup.ts',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: STUDIO,
    browserName: 'chromium',
    trace: 'retain-on-failure',
  },
});
