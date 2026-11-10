// The accessibility check (axe-core) of what a page shows now: its serious and critical problems, one line each, with
// the first few elements they were found on. A test ends with expect(problems).toEqual([]). With AXE_LOG set, every
// problem found (any impact) is also added to that file, to count them.

import { appendFileSync } from 'node:fs';
import AxeBuilder from '@axe-core/playwright';
import type { Page } from '@playwright/test';

export async function axe(page: Page, what: string) {
  const { violations } = await new AxeBuilder({ page }).analyze();
  if (process.env.AXE_LOG)
    for (const v of violations)
      appendFileSync(
        process.env.AXE_LOG,
        JSON.stringify({ what, id: v.id, impact: v.impact, nodes: v.nodes.length }) + '\n',
      );
  return violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map(
      (v) =>
        `${what}: ${v.id} (${v.impact}, ${v.nodes.length}×) ${v.nodes
          .slice(0, 3)
          .map((n) => n.target.join(' ') + (process.env.AXE_DETAIL ? ` [${n.failureSummary ?? ''}]` : ''))
          .join(' | ')}`,
    );
}
