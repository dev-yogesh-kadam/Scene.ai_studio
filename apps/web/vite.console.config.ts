// The admin console: built into dist/console/, which the backend serves on the console's own port only.
// `npm run dev:console` serves it on http://localhost:5174 with /api sent to the console (SCENE_CONSOLE_URL).

import { defineConfig } from 'vite';
import { site } from './vite.site.ts';

export default defineConfig(
  site({ name: 'console', port: 5174, backend: process.env.SCENE_CONSOLE_URL || 'http://localhost:8090' }),
);
