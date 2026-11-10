// Light or dark: the phone's setting, or the one chosen in Account (kept in this browser). Read once when the site
// opens (the colours are fixed for the visit), so a change shows when it is opened again.
import { Appearance } from 'react-native';

export type Choice = 'system' | 'dark' | 'light';

const KEY = 'scene.appearance';

export function chosen(): Choice {
  try {
    const saved = globalThis.localStorage?.getItem(KEY);
    return saved === 'dark' || saved === 'light' ? saved : 'system';
  } catch {
    return 'system';
  }
}

export function choose(choice: Choice) {
  try {
    globalThis.localStorage?.setItem(KEY, choice);
  } catch {
    // stays as it was
  }
}

/** The look this visit uses. */
export const scheme: 'dark' | 'light' = (() => {
  const choice = chosen();
  if (choice !== 'system') return choice;
  return Appearance.getColorScheme() === 'light' ? 'light' : 'dark';
})();
