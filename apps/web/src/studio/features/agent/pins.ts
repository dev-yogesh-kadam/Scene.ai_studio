// What the "Workflows for this chat" menu offers: a tab for each kind (Image, Video, Audio, Upscale), and in each the
// generation server's models one by one, then ComfyUI's workflows, never mixed. A pin is a workflow's id, or a model's
// "<workflow id>#<model>" (jobForm.pickValue); the agent turn reads both (workspace.py, chat_pins).

import type { ModelInfo, WorkflowRow } from '../jobs/jobForm';

export const PIN_KINDS = [
  { id: 'image', label: 'Image', icon: 'image' },
  { id: 'video', label: 'Video', icon: 'video' },
  { id: 'audio', label: 'Audio', icon: 'audio' },
  { id: 'upscaler', label: 'Upscale', icon: 'upscale' },
] as const;

export type PinEntry = {
  value: string; // the pin: a workflow id or "<workflow id>#<model>"
  title: string;
  about: string; // one sentence: what it is for
  meta: string[]; // its best resolution, its lengths: "4K", "4–15 s"
  sound: boolean; // makes sound with the picture
};

export type PinTab = { kind: string; label: string; icon: string; models: PinEntry[]; workflows: PinEntry[] };

/** The first sentence of a description or a model's hint, without its prices (no money talk in the agent). */
export function aboutOf(text: string) {
  const first = (text || '').split(/(?<=\.)\s+/)[0] || '';
  return /credit/i.test(first) ? '' : first.trim();
}

/** Its lengths in words, "4–15 s": from the server's list, else from the hint ("4–30 s"). */
export function secondsOf(model: Pick<ModelInfo, 'seconds'> | null, text: string) {
  const span = model?.seconds;
  if (span?.min != null && span?.max != null)
    return span.min === span.max ? `${span.min} s` : `${span.min}–${span.max} s`;
  const said = /(\d+(?:\.\d+)?)\s*(?:–|-|to)\s*(\d+(?:\.\d+)?)\s*(?:s|seconds)\b/i.exec(text || '');
  return said ? `${said[1]}–${said[2]} s` : '';
}

/** The best of its resolutions, as people say it: "4K" for 2160p, "1080p", "2K". */
export function bestResolution(resolutions: string[]) {
  const size = (r: string) => {
    const k = /^(\d+(?:\.\d+)?)\s*k$/i.exec(r);
    if (k) return Number(k[1]) * 1000;
    const p = /^(\d+)p$/i.exec(r);
    return p ? Number(p[1]) * (16 / 9) : 0; // a video's height, as a width to set beside 1K/2K/4K
  };
  const best = [...(resolutions || [])].sort((a, b) => size(b) - size(a))[0];
  if (!best) return '';
  return best.toLowerCase() === '2160p' ? '4K' : best;
}

function modelEntry(row: WorkflowRow, model: { id: string; label: string }, info?: ModelInfo): PinEntry {
  const hint = info?.about || '';
  return {
    value: `${row.id}#${model.id}`,
    title: info?.name || model.label,
    about: aboutOf(info?.best_for || hint),
    meta: [bestResolution(info?.resolutions || []), secondsOf(info || null, hint)].filter(Boolean),
    sound: !!info && row.kind === 'video' && info.sound !== 'never',
  };
}

function workflowEntry(row: WorkflowRow): PinEntry {
  const text = row.description || '';
  return {
    value: row.id,
    title: row.title,
    about: aboutOf(text),
    meta: [secondsOf(null, text)].filter(Boolean),
    sound: false,
  };
}

/** The tabs of the menu, only the kinds there is something to pick in. In a tab: the generation server's models in
 * their own order (the order the server gives them, its best first), then the single-model tools (a voiceover, music
 * …), then ComfyUI's workflows by name. */
export function pinTabs(rows: WorkflowRow[], models: Record<string, ModelInfo[]>): PinTab[] {
  const usable = rows.filter((w) => !w.error);
  return PIN_KINDS.map((k) => {
    const mine = usable.filter((w) => w.kind === k.id);
    const generation = mine.filter((w) => w.source === 'generation');
    const many = generation.flatMap((w) =>
      (w.models || []).map((m) =>
        modelEntry(
          w,
          m,
          (models[w.id] || []).find((i) => i.model === m.id),
        ),
      ),
    );
    const single = generation.filter((w) => !w.models?.length).map(workflowEntry);
    const workflows = mine
      .filter((w) => w.source !== 'generation')
      .map(workflowEntry)
      .sort((a, b) => a.title.localeCompare(b.title));
    return { kind: k.id, label: k.label, icon: k.icon, models: [...many, ...single], workflows };
  }).filter((t) => t.models.length || t.workflows.length);
}

/** The kind of a pin ("video" of "video/generation_video#kling_4_0"). */
export const kindOfPin = (pin: string) => pin.split('/', 1)[0];

/** The pins with one ticked or unticked. */
export const togglePin = (pins: string[], value: string) =>
  pins.includes(value) ? pins.filter((p) => p !== value) : [...pins, value];

/** The pins without those of one kind: the agent selects that kind again. */
export const clearKind = (pins: string[], kind: string) => pins.filter((p) => kindOfPin(p) !== kind);
