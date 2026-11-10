// The studio: built into dist/studio/, which the backend serves on the studio's port when web_app is "react".
// `npm run dev` serves it on http://localhost:5173 with /api sent to a running studio (SCENE_STUDIO_URL).

import { defineConfig } from 'vite';
import { site } from './vite.site.ts';

export default defineConfig(
  site({ name: 'studio', port: 5173, backend: process.env.SCENE_STUDIO_URL || 'http://localhost:8080' }),
);
