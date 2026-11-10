// What the landing page and the sign-in pages share: the camera's readouts, the timecode, and the first prompt a
// visitor typed before having an account.

/** The camera's readouts for each scene: lens and stop, sensitivity and shutter, colour temperature. */
export const READOUT: Record<string, string[]> = {
  rooftop: ['35mm · T2.0', 'ISO 800 · 1/48', '3200K'],
  neon: ['24mm · T1.4', 'ISO 1600 · 1/48', '5600K'],
  desert: ['85mm · T5.6', 'ISO 100 · 1/96', '6500K'],
  deep: ['18mm · T2.8', 'ISO 3200 · 1/48', '4300K'],
};

/** The frame counter of the camera: hours, minutes, seconds and frames at 24 a second. */
export function frameTimecode(frames: number) {
  const two = (n: number) => String(n).padStart(2, '0');
  return `${two(Math.floor(frames / 86400) % 24)}:${two(Math.floor(frames / 1440) % 60)}:${two(Math.floor(frames / 24) % 60)}:${two(frames % 24)}`;
}

/** The prompt a visitor typed before having an account travels in the address (?prompt=) from the landing page to
 *  the sign-in pages and on to Home, where it fills the prompt box: the first thing they see inside is their own shot,
 *  ready to make. In the address it survives a reload and belongs to that one visit. */
export function withPrompt(path: string, text: string | null) {
  const kept = (text || '').trim().slice(0, 2000);
  return kept ? `${path}?${new URLSearchParams({ prompt: kept })}` : path;
}
export const promptOf = (search: string) => new URLSearchParams(search).get('prompt')?.trim() || '';

/** The Motion setting (theme.js), or the computer asking for less motion. */
export const calmNow = () =>
  document.documentElement.dataset.motion === 'calm' || matchMedia('(prefers-reduced-motion: reduce)').matches;
