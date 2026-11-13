// Where everything goes on the canvas, worked out from the saved layout, the library, the jobs and the NeuralCore.
// Every shot is a row. Work made from scratch starts a new row at the bottom; work made from a frame (continued from
// it, re-run, trimmed, split) joins that frame's row at the right end. A numbered shot's takes are one stack at the
// left of its row. The boards left of the shots hold the NeuralCore's entries, the outputs and the final video.
// Pure: it returns a new layout and changes nothing it is given.

import type { Job } from '@scene/shared/types/api';
import type { Item } from '../../../common/media/item';
import {
  ACTIVE,
  BOARD_HEAD,
  BOARD_LABEL,
  BOARD_PAD,
  BOARDS,
  ENTRY_NAME,
  FAILED_SHOWN,
  FINAL_CUTS,
  FRAME,
  GAP,
  LABEL,
  SLATE,
  STACK_SHOWN,
  STACK_STEP,
  heightOf,
  parentOf,
  shotNumber,
  stacked,
  type Band,
  type BoardCard,
  type Key,
  type KitEntry,
  type Layout,
  type Placed,
  type Row,
  type Spot,
  type Stack,
} from './geometry';

/** A job as the live connection gives it, with the settings it was sent with. */
export type CanvasJob = Job & { settings?: Record<string, unknown>; error?: string; reason?: string; summary?: string };

export type OnBoard = { board: string; name: string; stack?: Stack };

export type Arranged = {
  layout: Layout;
  spots: Map<Key, Spot>;
  bands: Band[];
  cards: BoardCard[];
  onBoard: Map<number, OnBoard>;
  jobs: CanvasJob[]; // the jobs drawn as frames: running, waiting, or failed a short while ago
};

type Input = {
  layout: Layout;
  items: Item[];
  jobs: CanvasJob[];
  entries: KitEntry[];
  placed: Placed;
  project: number;
  now: number; // seconds
};

const copy = (layout: Layout): Layout => ({
  rows: layout.rows.map((row) => ({ ...row, keys: [...row.keys] })),
  count: layout.count,
  picks: { ...layout.picks },
});

/** The board a name given by a job goes on: one of the usual boards by its label ("Characters"), or one of its own. */
const boardOf = (name: string) => {
  const known = BOARDS.find(([, label]) => label.toLowerCase() === String(name).toLowerCase());
  return known ? known[0] : 'named:' + name;
};

export function arrange({ layout: saved, items, jobs: all, entries, placed, project, now }: Input): Arranged {
  const layout = copy(saved);
  const mine = (j: CanvasJob) => !project || j.project_id === project;
  const jobs = all.filter(
    (j) =>
      (ACTIVE.includes(j.status) || (j.status === 'failed' && j.finished && now - j.finished < FAILED_SHOWN)) &&
      mine(j),
  );
  const known = new Set(items.map((i) => i.id));
  // A job that has just finished keeps its place until what it made comes in (a moment later), so the result lands
  // where the job was and the shots never trade places. Two minutes at most: a job may make nothing to show here.
  const landing = all.filter(
    (j) =>
      j.status === 'done' && mine(j) && j.finished && now - j.finished < 120 && !items.some((i) => i.job_id === j.id),
  );
  const live = new Set([...jobs, ...landing].map((j) => 'job:' + j.id));

  const rowOf = (key: Key) => layout.rows.find((row) => row.keys.includes(key));
  const newRow = () => layout.rows[layout.rows.push({ id: ++layout.count, name: '', keys: [] }) - 1];
  // The row of a numbered shot, made when its first take comes.
  const shotRow = (n: number) => layout.rows.find((row) => row.shot === n) || Object.assign(newRow(), { shot: n });

  const onBoard = new Map<number, OnBoard>();
  for (const e of entries)
    if (e.item && known.has(e.item))
      onBoard.set(e.item, { board: e.tag && e.tag in BOARD_LABEL ? e.tag : 'other', name: e.name });
  for (const item of items)
    if (FINAL_CUTS.includes(item.workflow) && !onBoard.has(item.id))
      onBoard.set(item.id, { board: 'final', name: item.name });
  // A result its job put on a named board ("Characters", "Outputs") sits there, on the stack of what it is a version of.
  const named = new Map(items.map((i) => [i.id, i]));
  for (const board of placed.boards) {
    for (const s of board.stacks || []) {
      const members = (s.items || []).filter((id) => known.has(id));
      if (!members.length) continue;
      const stack = { key: `board:${board.name}:${s.group}`, members };
      // A finished cut placed on Outputs before Final video was a board of its own moves there.
      const home = FINAL_CUTS.includes(named.get(members[0])!.workflow) ? 'final' : boardOf(board.name);
      for (const id of members) onBoard.set(id, { board: home, name: named.get(id)!.name, stack });
    }
  }
  for (const item of [...items].reverse()) {
    // oldest first, so shots are numbered in the order they were made
    if (onBoard.has(item.id)) continue;
    const n = shotNumber(item.settings);
    if (n) {
      // a numbered shot is always in its own row, wherever it was dragged
      const row = shotRow(n);
      if (!row.keys.includes(item.id)) {
        for (const other of layout.rows) other.keys = other.keys.filter((key) => key !== item.id);
        row.keys.push(item.id);
      }
      continue;
    }
    if (rowOf(item.id)) continue;
    const held = item.job_id && rowOf('job:' + item.job_id); // finished work takes the place its job was holding
    if (held) held.keys.splice(held.keys.indexOf('job:' + item.job_id), 0, item.id);
    else (rowOf(parentOf(item.settings) ?? '') || newRow()).keys.push(item.id);
  }
  for (const job of [...jobs].reverse()) {
    if (rowOf('job:' + job.id) || items.some((i) => i.job_id === job.id)) continue;
    const n = shotNumber(job.settings);
    (n ? shotRow(n) : rowOf(parentOf(job.settings) ?? '') || newRow()).keys.push('job:' + job.id);
  }
  for (const row of layout.rows)
    row.keys = row.keys.filter((key) =>
      typeof key === 'number' ? known.has(key) && !onBoard.has(key) : live.has(key),
    );
  layout.rows = layout.rows.filter((row) => row.keys.length);
  // Numbered shots first, in the order of their numbers; the other rows after them, as they were.
  layout.rows = [
    ...layout.rows.filter((row) => row.shot).sort((a, b) => (a.shot ?? 0) - (b.shot ?? 0)),
    ...layout.rows.filter((row) => !row.shot),
  ];
  for (const key of Object.keys(layout.picks))
    if (!layout.rows.some((row) => `shot:${row.shot}` === key) && !key.startsWith('board:')) delete layout.picks[key];

  const heights = new Map(items.map((i) => [i.id as Key, heightOf(i)]));
  const jobOf = new Map(all.map((j) => ['job:' + j.id, j]));
  const settingsOf = (key: Key) => (typeof key === 'number' ? named.get(key)?.settings : jobOf.get(key)?.settings);
  const madeAt = (key: Key) =>
    (typeof key === 'number' ? named.get(key)?.created : jobOf.get(String(key))?.created) || 0;
  const sizeOf = (key: Key) => heights.get(key) || heightOf();
  const spots = new Map<Key, Spot>();
  const bands: Band[] = [];

  // Spots for a stack whose top is at (x, y): earlier takes behind it, each a little up and to the right.
  const stackSpots = (stack: Stack, order: Key[], x: number, y: number, extra: Partial<Spot> = {}) =>
    order.forEach((key, depth) => {
      const takeNo = stack.members.length - stack.members.indexOf(key); // the oldest is take 1
      const shown = Math.min(depth, STACK_SHOWN);
      spots.set(key, {
        x: x + shown * STACK_STEP,
        y: y - shown * STACK_STEP,
        h: sizeOf(key),
        depth,
        stack,
        takeNo,
        label: stack.shot ? `Take ${takeNo} of ${stack.members.length}` : '',
        ...extra,
      });
    });

  let y = 0;
  for (const row of layout.rows) {
    const sizes = row.keys.map(sizeOf);
    // A numbered row's takes of its shot are one stack at the left, the newest on top; the rest of the row (work made
    // from them: a trim, an upscale) follows it.
    const members = row.shot
      ? row.keys.filter((key) => shotNumber(settingsOf(key)) === row.shot).sort((a, b) => madeAt(b) - madeAt(a))
      : [];
    const rest = row.keys.filter((key) => !members.includes(key));
    if (members.length) {
      const stack = { key: `shot:${row.shot}`, members, shot: row.shot };
      stackSpots(stack, stacked(layout, stack.key, members), 0, y);
    }
    rest.forEach((key, i) => spots.set(key, { x: (i + (members.length ? 1 : 0)) * (FRAME + GAP), y, h: sizeOf(key) }));
    bands.push({ row, y, h: Math.max(...sizes) });
    y += Math.max(...sizes) + SLATE + GAP;
  }

  const cards = placeBoards({ layout, items, entries, placed, onBoard, bands, heights, spots, stackSpots });
  return { layout, spots, bands, cards, onBoard, jobs };
}

type BoardInput = {
  layout: Layout;
  items: Item[];
  entries: KitEntry[];
  placed: Placed;
  onBoard: Map<number, OnBoard>;
  bands: Band[];
  heights: Map<Key, number>;
  spots: Map<Key, Spot>;
  stackSpots: (stack: Stack, order: Key[], x: number, y: number, extra?: Partial<Spot>) => void;
};

type Entry = { key: Key; name: string; h: number; lift?: number; stack?: Stack; order?: Key[]; entry?: KitEntry };

// The boards, side by side left of the names of the shots, their tops level with the first shot. Each holds its
// entries two to a row: the name of the entry above its frame.
function placeBoards({ layout, items, entries, placed, onBoard, bands, heights, spots, stackSpots }: BoardInput) {
  const boards: [string, string][] = [
    ...BOARDS,
    ...placed.boards
      .filter((b) => boardOf(b.name).startsWith('named:'))
      .map((b): [string, string] => ['named:' + b.name, b.name]),
  ];
  const groups = new Map<string, Entry[]>(boards.map(([id]) => [id, []]));
  for (const item of items) {
    const where = onBoard.get(item.id);
    if (!where) continue;
    // A stack is one card: its top take, with the others behind it.
    const order =
      where.stack && where.stack.members.length > 1 ? stacked(layout, where.stack.key, where.stack.members) : null;
    if (order && order[0] !== item.id) continue;
    // The takes behind peek out above it: the card is that much taller, so they stay clear of the entry's name.
    const lift = order ? Math.min(order.length - 1, STACK_SHOWN) * STACK_STEP : 0;
    (groups.get(where.board) || groups.get('other')!).push({
      key: item.id,
      name: where.name,
      h: (heights.get(item.id) || heightOf()) + lift,
      lift,
      stack: order ? where.stack : undefined,
      order: order ?? undefined,
    });
  }
  for (const e of entries) {
    if (e.item && onBoard.has(e.item)) continue; // shown by its library item
    const board = e.tag && e.tag in BOARD_LABEL ? e.tag : 'other';
    groups
      .get(board)!
      .push({ key: 'kit:' + e.id, name: e.name, h: e.kind === 'image' ? Math.round(FRAME * 0.75) : 96, entry: e });
  }
  const used = boards.filter(([id]) => groups.get(id)!.length);
  const sizes = used.map(([id, label]) => {
    const list = groups.get(id)!;
    const cols = list.length > 1 ? 2 : 1;
    const rows: Entry[][] = [];
    for (let i = 0; i < list.length; i += cols) rows.push(list.slice(i, i + cols));
    const w = BOARD_PAD * 2 + cols * FRAME + ((cols - 1) * GAP) / 2;
    const h =
      BOARD_HEAD +
      BOARD_PAD +
      rows.reduce((sum, row) => sum + ENTRY_NAME + Math.max(...row.map((e) => e.h)) + SLATE + GAP / 2, 0);
    return { label, list, rows, w, h };
  });
  const total = sizes.reduce((sum, s) => sum + s.w + GAP, 0);
  let x = -LABEL - GAP - total;
  const top = bands.length ? bands[0].y - GAP / 3 : 0;
  const cards: BoardCard[] = [];
  for (const s of sizes) {
    const card: BoardCard = { label: s.label, count: s.list.length, x, y: top, w: s.w, h: s.h, names: [] };
    let y = top + BOARD_HEAD;
    for (const row of s.rows) {
      row.forEach((e, i) => {
        const ex = x + BOARD_PAD + i * (FRAME + GAP / 2);
        card.names.push({ text: e.name, x: ex, y });
        if (e.order && e.stack) stackSpots(e.stack, e.order, ex, y + ENTRY_NAME + (e.lift ?? 0), { board: true });
        else spots.set(e.key, { x: ex, y: y + ENTRY_NAME, h: e.h, board: true, entry: e.entry });
      });
      y += ENTRY_NAME + Math.max(...row.map((e) => e.h)) + SLATE + GAP / 2;
    }
    cards.push(card);
    x += s.w + GAP;
  }
  return cards;
}

/** Where a dragged frame would start a new shot: in the gap above the first shot or between two shots, near the line
 *  between them. The index the new shot takes, or -1 when the pointer is over a shot (it joins that one). */
export function gapAt(bands: Band[], y: number) {
  if (!bands.length) return -1;
  if (y > bands[0].y - GAP && y < bands[0].y + 12) return 0;
  for (let i = 1; i < bands.length; i++) {
    if (y > bands[i - 1].y + bands[i - 1].h + SLATE - 12 && y < bands[i].y + 12) return i;
  }
  return -1;
}

export const gapLine = (bands: Band[], i: number) =>
  i === 0 ? bands[0].y - GAP / 2 : (bands[i - 1].y + bands[i - 1].h + SLATE + bands[i].y) / 2;

/** Frames dropped at canvas x into the shot of `band` (or into the gap `gap`, a new shot there; or below the last
 *  row, a new shot at the end): the layout with them moved, at that place in the row. */
export function dropInto(
  saved: Layout,
  bands: Band[],
  ids: number[],
  drop: { x: number; middle: number },
  gap: number,
) {
  const layout = copy(saved);
  const band = bands.find((b) => drop.middle < b.y + b.h + SLATE + GAP / 2);
  const at = Math.max(0, Math.round(drop.x / (FRAME + GAP)));
  for (const row of layout.rows) row.keys = row.keys.filter((key) => !ids.includes(key as number));
  // Dropped on the line between two shots (or above the first): a new shot there, between them.
  const fresh: Row | null = gap >= 0 ? { id: ++layout.count, name: '', keys: [] } : null;
  const rowById = (id: number) => layout.rows.find((r) => r.id === id);
  if (fresh) layout.rows.splice(layout.rows.indexOf(rowById(bands[gap].row.id)!), 0, fresh);
  let row = fresh || (band ? rowById(band.row.id) : undefined);
  if (!row) row = layout.rows[layout.rows.push({ id: ++layout.count, name: '', keys: [] }) - 1];
  row.keys.splice(Math.min(fresh ? 0 : at, row.keys.length), 0, ...ids);
  return layout;
}

/** The arrow keys move the selected frames: left and right along their shot, up and down into the shot above or
 *  below (past the last, a new shot). Numbered takes stay in their stack. */
export function nudge(saved: Layout, ids: number[], key: 'ArrowLeft' | 'ArrowRight' | 'ArrowUp' | 'ArrowDown') {
  const layout = copy(saved);
  const rowIndex = (id: number) => layout.rows.findIndex((r) => r.keys.includes(id));
  const moving = ids.filter((id) => rowIndex(id) >= 0 && !layout.rows[rowIndex(id)].shot);
  if (!moving.length) return null;
  if (key === 'ArrowLeft' || key === 'ArrowRight') {
    const by = key === 'ArrowLeft' ? -1 : 1;
    for (const id of by < 0 ? moving : [...moving].reverse()) {
      const row = layout.rows[rowIndex(id)];
      const at = row.keys.indexOf(id);
      const to = at + by;
      if (to < 0 || to >= row.keys.length || moving.includes(row.keys[to] as number)) continue;
      row.keys.splice(at, 1);
      row.keys.splice(to, 0, id);
    }
    return layout;
  }
  const by = key === 'ArrowUp' ? -1 : 1;
  const from = rowIndex(moving[0]);
  let to = from + by;
  while (to >= 0 && to < layout.rows.length && layout.rows[to].shot) to += by; // a numbered shot holds its own takes
  if (to < 0) return null;
  for (const row of layout.rows) row.keys = row.keys.filter((k) => !moving.includes(k as number));
  if (to >= layout.rows.length) layout.rows.push({ id: ++layout.count, name: '', keys: [...moving] });
  else layout.rows[to].keys.push(...moving);
  layout.rows = layout.rows.filter((r) => r.keys.length);
  return layout;
}
