// What each version brought, newest first, for the "What's New" sheet shown once after an update (and in Account).
// Add an entry here whenever app.json's version goes up.
import Constants from 'expo-constants';

import type { IconName } from '@/components/Icon';

export type Release = { version: string; date: string; points: { icon: IconName; title: string; text: string }[] };

export const releases: Release[] = [
  {
    version: '1.2.0',
    date: 'November 2026',
    points: [
      { icon: 'globe', title: 'Right in your browser', text: 'Scene.ai on your phone is now a website: open the studio on your phone and you are here. No app to install.' },
      { icon: 'add-circle', title: 'Add to your home screen', text: 'In your browser’s menu, Add to Home screen: it opens full screen, like an app.' },
      { icon: 'desktop', title: 'The full studio, any time', text: 'Account › Open the Full Studio switches to the desktop studio on this phone.' },
    ],
  },
  {
    version: '1.1.0',
    date: 'November 2026',
    points: [
      { icon: 'chatbubble-ellipses', title: 'Talk to the agent', text: 'Open a module and Ask Agent. Approve its plans and watch each step render.' },
      { icon: 'cloud-upload', title: 'Start from your photos', text: 'Use a picture or video from your phone as a reference, or add it to your library.' },
      { icon: 'link', title: 'Share links', text: 'Send a link anyone can open, no account needed. It works for 30 days.' },
    ],
  },
];

/** The version people see (app.json). */
export const version = Constants.expoConfig?.version ?? '1.0.0';

const KEY = 'scene.whatsNew';

function lastSeen(): string | null {
  try {
    return globalThis.localStorage?.getItem(KEY) ?? null;
  } catch {
    return null;
  }
}

export function markSeen() {
  try {
    globalThis.localStorage?.setItem(KEY, version);
  } catch {
    // shown again next time; no harm
  }
}

/** The release to show now: this version's, once, after an update. A first visit shows nothing (it's all new). */
export function toShow(): Release | null {
  const seen = lastSeen();
  if (seen === null) {
    markSeen();
    return null;
  }
  return seen === version ? null : releases.find((r) => r.version === version) ?? null;
}
