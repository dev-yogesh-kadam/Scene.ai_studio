// What the "Workflows for this chat" menu offers: a tab for each kind (Image, Video, Audio, Upscale), and in each the
// providers' models, each a workflow of its own ("video/@seedance_2_5"). A pin is that workflow's id; the agent turn
// reads it (workspace.py, chat_pins).

import type { WorkflowRow } from '../jobs/jobForm';

export const PIN_KINDS = [
  { id: 'image', label: 'Image', icon: 'image' },
  { id: 'video', label: 'Video', icon: 'video' },
  { id: 'audio', label: 'Audio', icon: 'audio' },
  { id: 'upscaler', label: 'Upscale', icon: 'upscale' },
] as const;

export type PinEntry = {
  value: string; // the pin: a workflow id
  title: string;
  about: string; // one sentence: what it is for
  meta: string[]; // its lengths: "4–15 s"
};

export type PinTab = { kind: string; label: string; icon: string; models: PinEntry[] };

/** The first sentence of a description, without its prices (no money talk in the agent). */
export function aboutOf(text: string) {
  const first = (text || '').split(/(?<=\.)\s+/)[0] || '';
  return /credit/i.test(first) ? '' : first.trim();
}

/** Its lengths in words, "4–15 s", as its description says them ("4 to 15 seconds"); '' when it says none. */
export function secondsOf(text: string) {
  const said = /(\d+(?:\.\d+)?)\s*(?:–|-|to)\s*(\d+(?:\.\d+)?)\s*(?:s|seconds)\b/i.exec(text || '');
  return said ? `${said[1]}–${said[2]} s` : '';
}

function entryOf(row: WorkflowRow): PinEntry {
  const text = row.description || '';
  return {
    value: row.id,
    title: row.title,
    about: aboutOf(text),
    meta: [secondsOf(text)].filter(Boolean),
  };
}

/** The tabs of the menu, only the kinds there is something to pick in. In a tab: the models in the order the studio
 * lists them. */
export function pinTabs(rows: WorkflowRow[]): PinTab[] {
  const usable = rows.filter((w) => !w.error);
  return PIN_KINDS.map((k) => ({
    kind: k.id,
    label: k.label,
    icon: k.icon,
    models: usable.filter((w) => w.kind === k.id).map(entryOf),
  })).filter((t) => t.models.length);
}

/** The kind of a pin ("video" of "video/@seedance_2_5"). */
export const kindOfPin = (pin: string) => pin.split('/', 1)[0];

/** The pins with one ticked or unticked. */
export const togglePin = (pins: string[], value: string) =>
  pins.includes(value) ? pins.filter((p) => p !== value) : [...pins, value];

/** The pins without those of one kind: the agent selects that kind again. */
export const clearKind = (pins: string[], kind: string) => pins.filter((p) => kindOfPin(p) !== kind);
