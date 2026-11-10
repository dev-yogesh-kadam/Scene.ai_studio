import { describe, expect, it } from 'vitest';
import { createPath, handoffOf } from './handoff';

describe('hand-offs to Create travel in the address', () => {
  it('a re-run with its seed, from the canvas', () => {
    const path = createPath({ rerun: 12, reuseSeed: true, from: '/canvas' });
    expect(path).toBe('/create?rerun=12&seed=reuse&from=canvas');
    expect(handoffOf(path.split('?')[1])).toEqual({ rerun: 12, reuseSeed: true, prefill: undefined, from: '/canvas' });
  });

  it('a reference for a slot', () => {
    const path = createPath({
      prefill: { slot: 'first_frame', ref: { comfy_name: 'ref_a.png', name: 'A' }, parent: 7 },
    });
    expect(handoffOf(path.split('?')[1]).prefill).toEqual({
      slot: 'first_frame',
      ref: { comfy_name: 'ref_a.png', name: 'A' },
      parent: 7,
    });
  });

  it('nothing handed over is plain Create, and a seed alone means nothing', () => {
    expect(createPath({})).toBe('/create');
    expect(createPath({ reuseSeed: true })).toBe('/create');
    expect(handoffOf('')).toEqual({ rerun: null, reuseSeed: false, prefill: undefined, from: undefined });
  });
});
