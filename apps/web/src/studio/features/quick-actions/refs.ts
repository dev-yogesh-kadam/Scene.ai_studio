// The references of a Quick action's form: what fills each slot of the workflow (a file from this computer, a
// NeuralCore entry, a library item, the video selected on the canvas), and the picture references of an image model
// (REF 1, REF 2 ...), which each model names its own way in the prompt ("image 1", <ref_image_0>, <image1>).

import { inUse, type Slot, type Workflow } from '../jobs/jobForm';

/** What is in a slot. takes: the kind the slot takes; shown: how it is previewed (a video standing in for a picture
 *  shows its poster). cast: an always-on NeuralCore entry put there for the project. selection: the canvas's
 *  selection, followed until a file is put there by hand. */
export type Ref = {
  file?: File;
  assetId?: number;
  itemId?: number;
  name: string;
  url: string;
  takes?: string;
  shown?: string;
  cast?: boolean;
  selection?: boolean;
  seconds?: number; // a video's length, read by the browser: an upscale is priced by it
};

export const REMOVED = '[removed]';
const escapeRe = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
export const tokenRe = (token: string) => new RegExp(escapeRe(token) + '(?![\\w>])', 'g');

/** The picture reference slots of the model, in order (REF 1 first), when it makes pictures; else []. */
export function refSlots(wf: Workflow | null, kind: string, options: Record<string, string>) {
  if (kind !== 'image' || !wf) return [];
  const place = (r: Slot) => (r.order ? 1e9 + r.order : Number.parseFloat(r.node ?? '') || 0); // a list (ref_1, ref_2 …) in its order
  return wf.refs.filter((r) => r.kind === 'image' && inUse(r, options)).sort((a, b) => place(a) - place(b));
}

/** "REF 1" when a required reference is missing, else ''. */
export function missingRef(slots: Slot[], refs: Record<string, Ref>) {
  const at = slots.findIndex((s) => s.required && !refs[s.id]);
  return at < 0 ? '' : `REF ${at + 1}`;
}

/** The picture references carried to another model, in order, as many as it takes; the prompt rewritten in the new
 *  model's words, a reference it has no room for [removed]; and a note saying what was dropped. */
export function carryRefs(
  from: { wf: Workflow; slots: Slot[]; refs: Record<string, Ref> } | null,
  to: { wf: Workflow; slots: Slot[] },
  text: string,
) {
  const carried = from ? from.slots.map((s) => from.refs[s.id]).filter((r): r is Ref => !!r && !r.cast) : [];
  const refs: Record<string, Ref> = {};
  carried.slice(0, to.slots.length).forEach((ref, i) => {
    refs[to.slots[i].id] = ref;
  });
  const said = from?.wf.ref_naming ?? {};
  const saying = to.wf.ref_naming ?? {};
  if (carried.length && said.unique && said.tokens?.length && saying.unique && saying.tokens?.length) {
    const marks = carried.map((_, i) => `\u0000${i}\u0000`);
    carried.forEach((_, i) => {
      if (said.tokens![i]) text = text.replace(tokenRe(said.tokens![i]), marks[i]);
    });
    marks.forEach((mark, i) => {
      text = text.split(mark).join(i < to.slots.length && saying.tokens![i] ? saying.tokens![i] : REMOVED);
    });
  }
  const dropped = carried.length - Math.min(carried.length, to.slots.length);
  const room = to.slots.length;
  const note = !dropped
    ? ''
    : room
      ? `This model takes ${room} reference${room === 1 ? '' : 's'}; ${dropped} removed.`
      : `This model makes pictures from words only; ${dropped} reference${dropped === 1 ? '' : 's'} removed.`;
  return { refs, text, note, carried };
}

/** Take REF n out: the ones after it move up one, and so do their names in the prompt ("image 3" becomes "image 2").
 *  Where the prompt named the one taken out, it now says [removed], so no name points at the wrong picture. */
export function removeRef(wf: Workflow, slots: Slot[], refs: Record<string, Ref>, index: number, text: string) {
  const list = slots.map((s) => refs[s.id]).filter(Boolean);
  const [gone] = list.splice(index, 1);
  const next = { ...refs };
  for (const s of slots) delete next[s.id];
  list.forEach((ref, i) => {
    next[slots[i].id] = ref;
  });
  const naming = wf.ref_naming ?? {};
  const token = (naming.tokens ?? [])[index] || '';
  const said = !!token && tokenRe(token).test(text);
  if (naming.unique && naming.tokens?.length) {
    text = text.replace(tokenRe(naming.tokens[index]), REMOVED);
    for (let n = index + 1; n < naming.tokens.length; n += 1)
      text = text.replace(tokenRe(naming.tokens[n]), naming.tokens[n - 1]);
  }
  const note = !said
    ? ''
    : naming.unique
      ? `REF ${index + 1} was removed and the others moved up. The prompt says ${REMOVED} where it named it.`
      : `REF ${index + 1} was removed and the others moved up: check where the prompt said "${token}".`;
  return { refs: next, text, note, gone };
}

/** A frame from the canvas in a slot: the item as it is, a video in a picture slot as its last frame, a video in a
 *  sound slot as its sound. Null when the slot can't take it. */
export function itemRef(slot: Slot, item: { id: number; name: string; kind: string }): Ref | null {
  const fits =
    item.kind === slot.kind ||
    (slot.kind === 'image' && item.kind === 'video') ||
    (slot.kind === 'audio' && item.kind === 'video');
  if (!fits) return null;
  const picture = slot.kind === 'image' && item.kind === 'video';
  return {
    itemId: item.id,
    name: picture ? 'End of ' + item.name : item.name,
    takes: slot.kind,
    shown: picture ? 'image' : item.kind === 'video' && slot.kind === 'audio' ? 'audio' : item.kind,
    url: picture ? `/api/library/${item.id}/poster` : `/api/library/${item.id}/file`,
  };
}

/** "First frame (the video starts on this image)" -> "First frame" */
export const short = (label: string) => label.split(' (')[0];
