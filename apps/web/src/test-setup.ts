// Before every Vitest file: Testing Library's DOM matchers (toBeInTheDocument...), what jsdom lacks, and a clean page
// after each test.

import * as matchers from '@testing-library/jest-dom/matchers';
import { cleanup } from '@testing-library/react';
import { afterEach, expect } from 'vitest';

// Added to this file's own `expect`: jest-dom's '/vitest' entry extends the `expect` of the vitest that Node loads for
// it outside the test run, which is not the tests' one, so its matchers were never there.
expect.extend(matchers);

// jsdom has no media queries: every query answers "no" (a wide screen, full motion, the dark theme).
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList;
}

// jsdom does not scroll, and has no observers of what is in view or of sizes: nothing is ever seen or resized.
window.scrollTo = () => {};
class Unobserved {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return [];
  }
}
window.IntersectionObserver ??= Unobserved as unknown as typeof IntersectionObserver;
window.ResizeObserver ??= Unobserved as unknown as typeof ResizeObserver;

afterEach(() => cleanup());
