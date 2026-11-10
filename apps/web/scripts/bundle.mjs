// The size of the build: what a page loads before it can run (its first-load JavaScript and styles: the entry script
// and every file its page names, as the browser fetches them) and the files loaded later, when needed (Three.js, the
// canvas, the agent). The landing is part of the studio's first load: its styles' order in the one stylesheet decides
// which rule wins, and a file of its own would load them after the rest. With --check it fails when the studio's first-load JavaScript has grown more than
// 10% past the size kept in bundle-budget.json; with --save it keeps the size of this build there.
//
//   node scripts/bundle.mjs [--check] [--save] [dist folder]      (after npm run build; the build runs --check itself)
import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';

const here = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const dist = args.find((a) => !a.startsWith('--')) || join(here, '..', 'dist');
const BUDGET = join(here, '..', 'bundle-budget.json');
const GROWTH = 1.1; // how much the first-load JavaScript may grow past the size kept

const sizeOf = (file) => {
  const data = readFileSync(file);
  return { bytes: data.length, gzip: gzipSync(data, { level: 9 }).length };
};
const sum = (rows) =>
  rows.reduce((t, r) => ({ bytes: t.bytes + r.bytes, gzip: t.gzip + r.gzip }), { bytes: 0, gzip: 0 });

/** What the site's page makes the browser fetch before it runs: its module script, the modules it preloads, the styles. */
function firstLoad(site, page) {
  const html = readFileSync(join(dist, site, page), 'utf8');
  const files = (pattern) => [...html.matchAll(pattern)].map((m) => join(dist, site, m[1]));
  const js = [
    ...files(/<script type="module"[^>]*src="([^"]+)"/g),
    ...files(/<link rel="modulepreload"[^>]*href="([^"]+)"/g),
  ];
  const css = files(/<link rel="stylesheet"[^>]*href="([^"]+)"/g);
  return { js: sum(js.map(sizeOf)), css: sum(css.map(sizeOf)), files: js.length + css.length };
}

/** A file loaded when needed, found by the start of its name (Vite names a chunk after its module). */
function chunk(site, start) {
  const folder = join(dist, site, '_app');
  const found = readdirSync(folder).filter((f) => f.startsWith(start + '-') && f.endsWith('.js'));
  return found.length ? sum(found.map((f) => sizeOf(join(folder, f)))) : null;
}

const kb = (n) => (n / 1024).toFixed(1) + ' kB';
const report = {
  'studio: first load, JavaScript': firstLoad('studio', 'studio.html').js,
  'studio: first load, styles': firstLoad('studio', 'studio.html').css,
  'console: first load, JavaScript': existsSync(join(dist, 'console')) ? firstLoad('console', 'console.html').js : null,
  'Three.js, the landing 3D set (when idle)': chunk('studio', 'landing3d'),
  'canvas page': chunk('studio', 'CanvasPage'),
  'agent (with the canvas)': chunk('studio', 'AgentTabs'),
};
console.log('Bundle sizes (minified; gzip as sent)');
for (const [name, size] of Object.entries(report))
  console.log(
    `  ${name.padEnd(44)} ${size ? `${kb(size.bytes).padStart(10)}  ${kb(size.gzip).padStart(9)} gzip` : '—'}`,
  );

const first = report['studio: first load, JavaScript'].bytes;
if (args.includes('--save')) {
  writeFileSync(BUDGET, JSON.stringify({ studio_first_load_js: first }, null, 2) + '\n');
  console.log(`Kept ${kb(first)} as the studio's first-load JavaScript in bundle-budget.json.`);
}
if (args.includes('--check')) {
  const kept = JSON.parse(readFileSync(BUDGET, 'utf8')).studio_first_load_js;
  const most = Math.round(kept * GROWTH);
  if (first > most) {
    console.error(
      `The studio's first-load JavaScript is ${kb(first)}, more than ${kb(most)} (${kb(kept)} kept in ` +
        'bundle-budget.json, + 10%). Load the new code when it is needed (a lazy import), or, if the growth is ' +
        'meant, keep the new size: node scripts/bundle.mjs --save',
    );
    process.exit(1);
  }
  console.log(`First-load JavaScript within its budget: ${kb(first)} of at most ${kb(most)}.`);
}
