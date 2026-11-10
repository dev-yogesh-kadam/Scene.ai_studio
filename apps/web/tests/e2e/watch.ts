// What a page says went wrong while a test used it: errors in its console (a blocked script or style says so there),
// uncaught exceptions, and Content-Security-Policy violations. A test ends with expect(problems).toEqual([]).

import type { Page } from '@playwright/test';

export function watch(page: Page) {
  const problems: string[] = [];
  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    // Asking who is signed in answers 401 to someone who is not: the browser logs it, and it is how the page knows.
    // (The studio's /api/auth/me, the console's /api/console/me.)
    const whoAsked = /\/api\/(auth|console)\/me$/.test(message.location().url);
    if (message.text().startsWith('Failed to load resource') && whoAsked) return;
    problems.push(`console: ${message.text()} ${message.location().url}`);
  });
  page.on('pageerror', (error) => problems.push(`exception: ${error.message}`));
  // A violation is reported to the page as an event before any console line: listen from the first script on.
  void page.addInitScript(() => {
    document.addEventListener('securitypolicyviolation', (event) => {
      console.error(`CSP violation: ${event.violatedDirective} blocked ${event.blockedURI}`);
    });
  });
  return problems;
}
