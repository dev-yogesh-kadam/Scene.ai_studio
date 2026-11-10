// End-to-end tests (Playwright, Chromium only) against a studio of their own: the React build served by this working
// tree's backend, a new database, and the fake ComfyUI. Build first: `npm run e2e` does both.

import { defineConfig } from '@playwright/test';

// Ports from SCENE_TEST_PORT_BASE (default 8100: studio 8281, console 8290, fake ComfyUI 8299), see tests/support/studio.mjs.
export const PORT_BASE = Number(process.env.SCENE_TEST_PORT_BASE || 8100);
export const STUDIO = `http://127.0.0.1:${PORT_BASE + 181}`;
export const CONSOLE = `http://127.0.0.1:${PORT_BASE + 190}`;

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
