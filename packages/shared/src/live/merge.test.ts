import { describe, expect, it, vi } from 'vitest';
import { batcher, mergeById, mergeList } from './merge';

describe('mergeList', () => {
  const a = { id: 'a', status: 'running', progress: 0.2 };
  const b = { id: 'b', status: 'queued', progress: 0 };

  it('keeps the very same list when nothing changed', () => {
    const was = [a, b];
    expect(mergeList(was, [{ ...a }, { ...b }])).toBe(was);
  });

  it('keeps the unchanged jobs and takes the changed one', () => {
    const was = [a, b];
    const next = mergeList(was, [{ ...a, progress: 0.5 }, { ...b }]);
    expect(next).not.toBe(was);
    expect(next[0]).toEqual({ ...a, progress: 0.5 });
    expect(next[1]).toBe(b);
  });

  it('sees a job added, removed or moved', () => {
    expect(mergeList([a], [a, b])).toHaveLength(2);
    expect(mergeList([a, b], [a])).toEqual([a]);
    const moved = mergeList([a, b], [{ ...b }, { ...a }]);
    expect(moved[0]).toBe(b);
    expect(moved[1]).toBe(a);
  });

  it('starts a list from nothing', () => {
    expect(mergeList(undefined, [a])).toEqual([a]);
  });
});

describe('mergeById', () => {
  it('keeps the same map when the plans heard are as they were', () => {
    const was = new Map([[1, { id: 1, state: 'running' }]]);
    expect(mergeById(was, [{ id: 1, state: 'running' }])).toBe(was);
    const next = mergeById(was, [{ id: 1, state: 'done' }]);
    expect(next).not.toBe(was);
    expect(next.get(1)).toEqual({ id: 1, state: 'done' });
  });
});

describe('batcher', () => {
  it('applies the calls made close together at once', () => {
    vi.useFakeTimers();
    const apply = vi.fn();
    const { add } = batcher<number>(apply, 100);
    add(1);
    add(2);
    add(3);
    expect(apply).not.toHaveBeenCalled();
    vi.advanceTimersByTime(120);
    expect(apply).toHaveBeenCalledTimes(1);
    expect(apply).toHaveBeenCalledWith([1, 2, 3]);
    add(4);
    vi.advanceTimersByTime(120);
    expect(apply).toHaveBeenLastCalledWith([4]);
    vi.useRealTimers();
  });
});
