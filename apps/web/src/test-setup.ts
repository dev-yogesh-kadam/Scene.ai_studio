// Before every Vitest file: Testing Library's DOM matchers (toBeInTheDocument...), what jsdom lacks, and a clean page
// after each test.

import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

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
