// Writes the design tokens (tokens.json, the one source) out for each app: the web's CSS variables and the phone site's
// theme values. Both written files say not to edit them. With --check it writes nothing and fails when one of them is
// not what tokens.json makes (someone edited it by hand, or forgot to run this).
//
//   npm run tokens                  (at the root)
//   node packages/shared/tokens/build.mjs --check

import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import prettier from 'prettier';

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, '../../..');
const tokens = JSON.parse(readFileSync(join(here, 'tokens.json'), 'utf8'));
const WARNING = 'Made from packages/shared/tokens/tokens.json by npm run tokens: change it there, not here.';

const vars = (map, scheme) =>
  [...Object.entries(map).map(([name, value]) => `--${name}: ${value};`), `color-scheme: ${scheme};`].join('\n');

const css = `/* ${WARNING} */

/* The dark theme, the default. */
:root {
${vars(tokens.web.dark, 'dark')}
}

/* The light theme: the computer's own when nothing is chosen, or chosen (data-theme="light"). */
@media (prefers-color-scheme: light) {
  :root:not([data-theme='dark']) {
${vars(tokens.web.light, 'light')}
  }
}
:root[data-theme='light'] {
${vars(tokens.web.light, 'light')}
}
`;

const literal = (value) => JSON.stringify(value, null, 2);
const phone = `// ${WARNING}

export const dark = ${literal(tokens.phone.dark)};

export const light: typeof dark = ${literal(tokens.phone.light)};

export const spacing = ${literal(tokens.phone.spacing)} as const;

export const radius = ${literal(tokens.phone.radius)} as const;
`;

const outputs = [
  ['apps/web/src/common/styles/tokens.css', css, 'css'],
  ['packages/shared/src/tokens/phone.ts', phone, 'typescript'],
];

const config = await prettier.resolveConfig(join(repo, 'package.json'));
let stale = 0;
for (const [path, text, parser] of outputs) {
  const made = await prettier.format(text, { ...config, parser });
  const target = join(repo, path);
  if (process.argv.includes('--check')) {
    let now = '';
    try {
      now = readFileSync(target, 'utf8').replaceAll('\r\n', '\n');
    } catch {
      // not there: stale
    }
    if (now !== made) {
      console.error(`${path} is not what tokens.json makes. Run: npm run tokens`);
      stale += 1;
    }
  } else {
    writeFileSync(target, made);
    console.log(`Wrote ${path}`);
  }
}
if (stale) process.exit(1);
