// Whether the web app needs building: exits 0 when there is no build, or a file it is built from (apps/web and
// packages/shared) changed after it; 1 when the build is current. The start scripts build it then.
//
//   node apps/web/scripts/stale.mjs && npm run build -w apps/web

import { readdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const web = join(dirname(fileURLToPath(import.meta.url)), '..');
const built = (page) => {
  try {
    return statSync(join(web, 'dist', page)).mtimeMs;
  } catch {
    return 0;
  }
};
const builtAt = Math.min(built('studio/studio.html'), built('console/console.html'));

/** The newest change under `path`, a file or a folder. */
function newest(path) {
  const found = statSync(path, { throwIfNoEntry: false });
  if (!found) return 0;
  if (!found.isDirectory()) return found.mtimeMs;
  return Math.max(0, ...readdirSync(path).map((name) => newest(join(path, name))));
}

const sources = [
  'src',
  'public',
  'studio.html',
  'console.html',
  'package.json',
  'vite.site.ts',
  'vite.studio.config.ts',
  'vite.console.config.ts',
  '../../packages/shared/src',
].map((part) => newest(join(web, part)));
process.exit(!builtAt || Math.max(...sources) > builtAt ? 0 : 1);
