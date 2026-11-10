// This browser's own view: theme, motion, panel width, the last tab (and filters like them), kept in localStorage. Every
// read and write is guarded: in a browser that blocks storage they do nothing instead of throwing (S3). Choices that
// change what the studio does, or that someone else should see, are on the server (studio/userPrefs.ts).

export const prefs = {
  get(key: string, fallback = ''): string {
    try {
      return localStorage.getItem(key) ?? fallback;
    } catch {
      return fallback;
    }
  },
  set(key: string, value: string) {
    try {
      localStorage.setItem(key, value);
    } catch {
      // no storage: the choice lasts until the page is left
    }
  },
  remove(key: string) {
    try {
      localStorage.removeItem(key);
    } catch {
      // no storage
    }
  },
  /** Every key kept. */
  keys(): string[] {
    try {
      return Array.from({ length: localStorage.length }, (_, i) => localStorage.key(i) ?? '');
    } catch {
      return [];
    }
  },
};

/** The same, for this tab only (sessionStorage). */
export const tabPrefs = {
  get(key: string, fallback = ''): string {
    try {
      return sessionStorage.getItem(key) ?? fallback;
    } catch {
      return fallback;
    }
  },
  set(key: string, value: string) {
    try {
      sessionStorage.setItem(key, value);
    } catch {
      // no storage
    }
  },
};
