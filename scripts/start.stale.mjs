// What the start scripts (start.bat, start.sh) have to do again after a `git pull`: exits 0 when it is due, 1 when not.
//
//   node scripts/start.stale.mjs packages   the root's packages (npm workspaces) are not installed, or package-lock.json
//                                           or a workspace's package.json changed after the last `npm install`
//   node scripts/start.stale.mjs mobile     the phone site (apps/mobile) has no build, or a file it is built from changed
//                                           after it (apps/web/scripts/stale.mjs is the same for the web app)

import { readdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

/** When `path` was changed, 0 when it is not there. */
function changed(path) {
  return statSync(join(root, path), { throwIfNoEntry: false })?.mtimeMs ?? 0;
}

/** The newest change under `path`, a file or a folder. */
function newest(path) {
  const found = statSync(join(root, path), { throwIfNoEntry: false });
  if (!found) return 0;
  if (!found.isDirectory()) return found.mtimeMs;
  return Math.max(found.mtimeMs, ...readdirSync(join(root, path)).map((name) => newest(join(path, name))));
}

const checks = {
  // npm writes node_modules/.package-lock.json at the end of every install.
  packages: () => {
    const installed = changed('node_modules/.package-lock.json');
    const wanted = ['package.json', 'package-lock.json', 'apps/web/package.json', 'apps/mobile/package.json',
      'packages/shared/package.json'].map(changed);
    return !installed || Math.max(...wanted) > installed;
  },
  mobile: () => {
    const built = changed('apps/mobile/dist/index.html');
    const sources = ['apps/mobile/src', 'apps/mobile/assets', 'apps/mobile/public', 'apps/mobile/app.json',
      'apps/mobile/package.json', 'apps/mobile/tsconfig.json', 'packages/shared/src'].map(newest);
    return !built || Math.max(...sources) > built;
  },
};

const check = checks[process.argv[2]];
if (!check) {
  console.error('Say what to check: ' + Object.keys(checks).join(' or '));
  process.exit(2);
}
process.exit(check() ? 0 : 1);
