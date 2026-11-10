import { describe, expect, it } from 'vitest';
import type { Item } from '../../../common/media/item';
import { arrange, dropInto, gapAt, nudge, type CanvasJob } from './arrange';
import { readLayout, rowName, type Layout } from './geometry';

const item = (id: number, extra: Partial<Item> = {}): Item => ({
  id,
  name: `Item ${id}`,
  kind: 'image',
  workflow: 'image/flux',
  filename: `${id}.png`,
  created: id,
  context: { width: 1600, height: 900 },
  ...extra,
});

const job = (id: string, extra: Partial<CanvasJob> = {}) =>
  ({ id, name: id, workflow: 'image/flux', status: 'running', created: 10, project_id: 1, ...extra }) as CanvasJob;

const base = { entries: [], placed: { boards: [] }, project: 1, now: 1000, jobs: [] as CanvasJob[] };
const empty: Layout = { rows: [], count: 0, picks: {} };

describe('arrange', () => {
  it('starts a row for each new item, oldest first, and numbered shots first', () => {
    // the library lists the newest first
    const items = [item(3, { settings: { shot_number: 1 } }), item(2, { settings: { shot_number: 1 } }), item(1)];
    const { layout, spots, bands } = arrange({ ...base, layout: empty, items });
    expect(layout.rows.map((r) => [r.shot ?? null, r.keys])).toEqual([
      [1, [2, 3]],
      [null, [1]],
    ]);
    expect(bands).toHaveLength(2);
    // the newest take is on top of the stack, the earlier one behind it, up and to the right
    expect(spots.get(3)).toMatchObject({ x: 0, y: 0, depth: 0, label: 'Take 2 of 2' });
    expect(spots.get(2)).toMatchObject({ x: 6, y: -6, depth: 1, label: 'Take 1 of 2' });
    expect(rowName(layout.rows, layout.rows[1])).toBe('Shot 2');
  });

  it('keeps a picked take on top until a new take comes', () => {
    const items = [item(2, { settings: { shot_number: 1 } }), item(1, { settings: { shot_number: 1 } })];
    const picked = { rows: [], count: 0, picks: { 'shot:1': { key: 1, count: 2 } } };
    expect(arrange({ ...base, layout: picked, items }).spots.get(1)?.depth).toBe(0);
    const more = [item(5, { settings: { shot_number: 1 } }), ...items];
    expect(arrange({ ...base, layout: picked, items: more }).spots.get(5)?.depth).toBe(0);
  });

  it("puts work made from a frame into that frame's row, and a finished job's result where the job was", () => {
    const items = [item(2, { settings: { parent: 1 } }), item(1)];
    expect(arrange({ ...base, layout: empty, items }).layout.rows.map((r) => r.keys)).toEqual([[1, 2]]);
    const running = arrange({ ...base, layout: empty, items: [item(1)], jobs: [job('a')] });
    expect(running.layout.rows.map((r) => r.keys)).toEqual([[1], ['job:a']]);
    const landed = arrange({
      ...base,
      layout: running.layout,
      items: [item(4, { job_id: 'a' }), item(1)],
      jobs: [job('a', { status: 'done', finished: 999 })],
    });
    expect(landed.layout.rows.map((r) => r.keys)).toEqual([[1], [4]]);
  });

  it('shows a failed job for a day, and not after', () => {
    const failed = job('f', { status: 'failed', finished: 500 });
    expect(arrange({ ...base, layout: empty, items: [], jobs: [failed] }).jobs).toHaveLength(1);
    expect(arrange({ ...base, now: 500 + 86400, layout: empty, items: [], jobs: [failed] }).jobs).toHaveLength(0);
  });

  it("sits a NeuralCore entry's picture on its board, not in a shot", () => {
    const items = [item(2), item(1)];
    const entries = [{ id: 9, name: 'Meera', tag: 'character', kind: 'image', item: 1 }];
    const { layout, cards, spots } = arrange({ ...base, layout: empty, items, entries });
    expect(layout.rows.flatMap((r) => r.keys)).toEqual([2]);
    expect(cards.map((c) => [c.label, c.count])).toEqual([['Characters', 1]]);
    expect(spots.get(1)?.board).toBe(true);
  });

  it('reads a saved layout safely, keeping its shape', () => {
    expect(readLayout(null)).toEqual(empty);
    expect(readLayout({ rows: [{ id: 1, name: '', keys: [1] }, null, { keys: 'x' }], count: '3', picks: [] })).toEqual({
      rows: [{ id: 1, name: '', keys: [1] }],
      count: 3,
      picks: {},
    });
  });
});

describe('moving frames', () => {
  const two = arrange({ ...base, layout: empty, items: [item(2), item(1)] });

  it('drops into another shot, or into the gap between two as a new shot', () => {
    const moved = dropInto(two.layout, two.bands, [2], { x: 300, middle: 10 }, -1);
    expect(moved.rows.map((r) => r.keys)).toEqual([[1, 2], []]);
    const gap = gapAt(two.bands, two.bands[1].y - 10);
    expect(gap).toBe(1);
    const split = dropInto(two.layout, two.bands, [1], { x: 0, middle: 0 }, 0);
    expect(split.rows.map((r) => r.keys)).toEqual([[1], [], [2]]);
  });

  it('moves with the arrow keys along a shot and between shots', () => {
    const down = nudge(two.layout, [1], 'ArrowDown')!;
    expect(down.rows.map((r) => r.keys)).toEqual([[2, 1]]);
    const left = nudge(down, [1], 'ArrowLeft')!;
    expect(left.rows.map((r) => r.keys)).toEqual([[1, 2]]);
    const out = nudge(left, [2], 'ArrowDown')!;
    expect(out.rows.map((r) => r.keys)).toEqual([[1], [2]]);
    expect(nudge(out, [1], 'ArrowUp')).toBeNull(); // nothing above the first shot
  });
});
