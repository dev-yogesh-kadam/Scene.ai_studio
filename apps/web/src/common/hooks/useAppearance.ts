// Light, dark or the computer's own ('system'), and the Motion setting: 'full', 'calm', or 'system' (what the computer
// asks for). Kept in this browser for the next visit; public/theme.js applies both before the page paints.

import { useState } from 'react';
import type { Choice } from '../components/Segmented';
import { prefs } from '../prefs';

export type Theme = 'light' | 'dark' | 'system';
export type Motion = 'full' | 'calm' | 'system';

export const THEMES: Choice<Theme>[] = [
  { id: 'light', label: 'Light' },
  { id: 'dark', label: 'Dark' },
  { id: 'system', label: 'Auto', hint: 'Same as this computer' },
];
export const MOTIONS: Choice<Motion>[] = [
  { id: 'full', label: 'Full' },
  { id: 'calm', label: 'Less' },
  { id: 'system', label: 'Auto', hint: 'Same as this computer' },
];

declare global {
  interface Window {
    sceneMotion?: () => void; // set by public/theme.js
  }
}

export function applyTheme(theme: Theme) {
  if (theme === 'system') delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = theme;
  prefs.set('scene.theme', theme);
}

export function applyMotion(choice: Motion) {
  if (choice === 'system') prefs.remove('scene.motion');
  else prefs.set('scene.motion', choice);
  window.sceneMotion?.();
}

export const themeChoice = () => (prefs.get('scene.theme') || 'system') as Theme;
export const motionChoice = () => (prefs.get('scene.motion') || 'system') as Motion;

/** Calm motion (the Motion setting, or the computer's own on Auto) puts every animation at its end at once. */
export const reducedMotion = () => document.documentElement.dataset.motion === 'calm';

export function useAppearance() {
  const [theme, setTheme] = useState<Theme>(themeChoice);
  const [motion, setMotion] = useState<Motion>(motionChoice);
  return {
    theme,
    motion,
    setTheme: (t: Theme) => {
      applyTheme(t);
      setTheme(t);
    },
    setMotion: (m: Motion) => {
      applyMotion(m);
      setMotion(m);
    },
  };
}
