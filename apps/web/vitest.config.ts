// Unit and component tests (Vitest + Testing Library), in a browser-like document. End-to-end tests are Playwright's.

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: ['src/test-setup.ts'],
    css: { modules: { classNameStrategy: 'non-scoped' } },
  },
});
