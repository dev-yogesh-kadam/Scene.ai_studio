// Numbers and times in the studio's words, as the classic dom.js wrote them.

/** An amount of credits in words, outside the agent panel (which keeps its short "cr"): "1 credit", "1,250 credits". */
export const creditsText = (n: number | null | undefined) =>
  `${Number(n ?? 0).toLocaleString()} ${Number(n) === 1 ? 'credit' : 'credits'}`;

/** What a running job is doing, in words of a film set, from how far it is. */
export const phaseOf = (share: number) =>
  share < 0.02
    ? 'Setting up the shot'
    : share < 0.35
      ? 'Blocking the scene'
      : share < 0.7
        ? 'Rolling camera'
        : share < 0.95
          ? 'Developing frames'
          : 'Final touches';

export function duration(seconds: number | null | undefined) {
  if (seconds == null) return '';
  if (seconds < 90) return `${Math.round(seconds)} s`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} min`;
  return `${Math.floor(seconds / 3600)} h ${Math.round((seconds % 3600) / 60)} min`;
}

/** The first letters of a name's first two words, for a project that has no picture yet. */
export const initials = (name: string) =>
  name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => [...word][0])
    .join('')
    .toUpperCase();

/** How long ago, in a few characters: "just now", "8h ago", "3d ago"; a date once it is over a month. */
export function ago(timestamp: number) {
  const seconds = Date.now() / 1000 - timestamp;
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return Math.floor(seconds / 60) + 'm ago';
  if (seconds < 86400) return Math.floor(seconds / 3600) + 'h ago';
  if (seconds < 30 * 86400) return Math.floor(seconds / 86400) + 'd ago';
  return new Date(timestamp * 1000).toLocaleDateString([], { dateStyle: 'medium' });
}

export function when(timestamp: number) {
  return new Date(timestamp * 1000).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
}

/** The name on the browser tab: what is open (a project, a page), then the app. */
export function tabTitle(name?: string) {
  document.title = name ? `${name} · Scene.ai` : 'Scene.ai';
}
