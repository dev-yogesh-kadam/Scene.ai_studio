// The canvas's measures and the shapes its layout is made of. A frame is FRAME canvas units wide; its height follows
// the picture. The saved layout (GET/PUT /api/boards/canvas) is a Layout, exactly as the classic canvas saved it.

import type { Item } from '../../../common/media/item';

export const FRAME = 240; // width of every frame, in canvas units
export const SLATE = 24; // room under a frame for its line of facts
export const LABEL = 144; // room left of a row for the name of its shot
export const GAP = 48;
export const SNAP = 8;
export const MIN_ZOOM = 0.1;
export const MAX_ZOOM = 3; // 300%: close enough to check a face or a hand
export const ACTIVE = ['queued', 'running'];
// A job that failed stays on the canvas, where its result would have been, saying why, for this long: a frame that just
// vanished would look like the studio losing work.
export const FAILED_SHOWN = 24 * 3600;
export const STACK_STEP = 6; // how far each earlier take peeks out from behind the one on top, up and to the right
export const STACK_SHOWN = 3; // earlier takes drawn behind it; more are there, one switch away
export const BOARD_PAD = 20; // inside a board, around its frames
export const BOARD_HEAD = 64; // the board's title, with room for it to grow as the canvas zooms out
export const ENTRY_NAME = 22; // the name of an entry, above its frame

// The boards left of the shots, left to right: the final video (every clip patched into one), the outputs, then the
// module's NeuralCore by type. A picture that is a NeuralCore entry, or a finished cut, sits on its board and not in a
// shot row.
export const BOARDS: [string, string][] = [
  ['final', 'Final video'],
  ['outputs', 'Outputs'],
  ['character', 'Characters'],
  ['background', 'Locations'],
  ['prop', 'Props'],
  ['outfit', 'Outfits'],
  ['style', 'Styles'],
  ['voice', 'Voices'],
  ['script', 'Scripts'],
  ['other', 'Other'],
];
export const BOARD_LABEL: Record<string, string> = Object.fromEntries(BOARDS);
export const FINAL_CUTS = ['edit/assemble', 'edit/film']; // the whole film (backend/scene/placement.py FINISHED)

/** A key on the canvas: a library item id, 'job:<id>' while it is being made, or 'kit:<id>' for a NeuralCore file. */
export type Key = number | string;

/** One shot: its frames left to right. shot: the story shot number of a row the agent's numbered shots made. */
export type Row = { id: number; name: string; keys: Key[]; shot?: number };

/** The saved layout. picks: which take of a stack the user put on top, {stack key: {key, count}}; a new take (count
 *  changes) goes on top again. */
export type Layout = { rows: Row[]; count: number; picks: Record<string, { key: Key; count: number }> };

export type Stack = { key: string; members: Key[]; shot?: number };

/** Where its row puts a frame. On a stack: how deep it is, which take, and the stack. */
export type Spot = {
  x: number;
  y: number;
  h: number;
  depth?: number;
  stack?: Stack;
  takeNo?: number;
  label?: string;
  board?: boolean;
  entry?: KitEntry;
};

export type Band = { row: Row; y: number; h: number };

export type BoardCard = {
  label: string;
  count: number;
  x: number;
  y: number;
  w: number;
  h: number;
  names: { text: string; x: number; y: number }[];
};

export type KitEntry = {
  id: number;
  name: string;
  type?: string;
  tag?: string;
  kind: string;
  item?: number | null;
  url?: string;
};

/** Named boards and their stacks, as finished jobs placed them (GET /api/library/placement). */
export type Placed = { boards: { name: string; stacks?: { group: string; items?: number[] }[] }[] };

export const clamp = (n: number, low: number, high: number) => Math.max(low, Math.min(high, n));

export const heightOf = (item?: Item) => {
  const c = item?.context ?? {};
  return Math.round(FRAME * (c.width && c.height ? c.height / c.width : 9 / 16));
};

/** A frame's place in its shot, counted as takes from the left; a take on a stack says which of how many it is. */
export const take = (spot: Spot) => spot.label || `Take ${Math.round(spot.x / (FRAME + GAP)) + 1}`;

/** The number of the story shot a job was made for (its settings' shot_number, see backend/scene/placement.py), or
 *  null. Results with one sit in the row of that shot, rows in order of their numbers, and a retake stacks on it. */
export const shotNumber = (settings: unknown) => {
  const n = (settings as { shot_number?: unknown } | null | undefined)?.shot_number;
  return typeof n === 'number' && Number.isInteger(n) && n > 0 ? n : null;
};

/** The frame something was made from: sent with the job, or the first clip of an edit. */
export const parentOf = (settings: unknown): Key | null => {
  const s = settings as { parent?: Key; clips?: { id?: Key }[] } | null | undefined;
  return (s && (s.parent || (Array.isArray(s.clips) && s.clips[0] && s.clips[0].id))) || null;
};

/** What a row is called: the name given to it, its shot number, or, for a row with no number, the next numbers after
 *  the highest one, so two rows are never both called "Shot 3". */
export function rowName(rows: Row[], row: Row, plain = false) {
  if (row.name && !plain) return row.name;
  if (row.shot) return `Shot ${row.shot}`;
  const top = Math.max(0, ...rows.filter((r) => r.shot).map((r) => r.shot ?? 0));
  return `Shot ${top + rows.filter((r) => !r.shot).indexOf(row) + 1}`;
}

/** A stack's members put in the order they are drawn: the one on top first. The newest is on top unless the user
 *  switched to another take since the last one came. */
export function stacked(layout: Layout, key: string, members: Key[]) {
  const pick = layout.picks[key];
  const top = pick && pick.count === members.length && members.includes(pick.key) ? pick.key : members[0];
  return [top, ...members.filter((k) => k !== top)];
}

/** The layout as saved, made safe to use: rows with keys, a count, picks. */
export function readLayout(saved: unknown): Layout {
  const s = (saved ?? {}) as Partial<Layout>;
  return {
    rows: Array.isArray(s.rows) ? s.rows.filter((row) => row && Array.isArray(row.keys)) : [],
    count: Number(s.count) || 0,
    picks: s.picks && typeof s.picks === 'object' && !Array.isArray(s.picks) ? s.picks : {},
  };
}

/** The frames' outer edges, in canvas units. */
export function bounds(list: { x: number; y: number; h: number }[]) {
  return {
    x: Math.min(...list.map((b) => b.x)),
    y: Math.min(...list.map((b) => b.y)),
    right: Math.max(...list.map((b) => b.x + FRAME)),
    bottom: Math.max(...list.map((b) => b.y + b.h + SLATE)),
  };
}
