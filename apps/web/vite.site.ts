// What the studio's build and the admin console's build share. They are two separate builds on purpose: the console's
// code must never be in the studio's files, which are served on the port the internet reaches.

import react from '@vitejs/plugin-react';
import type { UserConfig } from 'vite';

type Site = {
  name: 'studio' | 'console';
  port: number; // the dev server's port
  backend: string; // where the dev server sends /api: the studio's port, or the console's
};

export function site({ name, port, backend }: Site): UserConfig {
  return {
    plugins: [react()],
    publicDir: 'public', // theme.js, fonts and images, served as they are at /theme.js, /fonts/..., /img/...
    // CSS Modules by Lightning CSS: class names are local to their component; keyframe names stay global (they were
    // unique in the one stylesheet already), so an animation named in one module can use keyframes from another.
    css: { transformer: 'lightningcss', lightningcss: { cssModules: { animation: false } } },
    build: {
      outDir: `dist/${name}`,
      emptyOutDir: true,
      assetsDir: '_app', // the folder the backend serves the build's hashed files from (main.py, BUILT_FOLDERS)
      assetsInlineLimit: 0, // no data: URLs: the page's policy allows fonts from this site only
      cssMinify: 'lightningcss',
      chunkSizeWarningLimit: 600, // Three.js (the landing's 3D set, ~510 kB) is a chunk of its own, loaded only when idle

      sourcemap: name === 'console', // the studio's port is the public one: no source maps there
      rolldownOptions: { input: `${name}.html` },
    },
    server: {
      port,
      strictPort: true,
      proxy: {
        '/api': { target: backend, changeOrigin: false, ws: true },
      },
    },
  };
}
