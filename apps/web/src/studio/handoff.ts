// What another page hands to Create when it opens it: an item whose settings to load (Re-run), with its seed (Reuse
// seed), a reference to put into a slot (Use as first frame, Continue), and the page to go back to. They travel in the
// address (/create?rerun=12&seed=reuse&from=canvas), never in shared state, where one left behind by an error leaked
// into the next visit (S5): they belong to that one visit, survive a reload and can be shared.

import type { NavigateFunction } from 'react-router';
import type { Item } from '../common/media/item';

export type Prefill = { slot: string; ref: { comfy_name: string; name: string }; parent?: number };

/** What a page asks Create for. */
export type HandoffLink = {
  rerun?: Item | number; // load this item's settings
  reuseSeed?: boolean; // with rerun: keep the seed it was made with
  prefill?: Prefill; // a reference to put into a slot
  from?: '/canvas'; // the page that opened Create, so Create can offer a way back to it
};

/** The same, as Create reads it from its address (the item to re-run by its id). */
export type Handoff = { rerun: number | null; reuseSeed: boolean; prefill?: Prefill; from?: string };

export function createPath(link: HandoffLink) {
  const query = new URLSearchParams();
  if (link.rerun) query.set('rerun', String(typeof link.rerun === 'number' ? link.rerun : link.rerun.id));
  if (link.rerun && link.reuseSeed) query.set('seed', 'reuse');
  if (link.prefill) {
    query.set('slot', link.prefill.slot);
    query.set('ref', link.prefill.ref.comfy_name);
    query.set('ref_name', link.prefill.ref.name);
    if (link.prefill.parent) query.set('parent', String(link.prefill.parent));
  }
  if (link.from === '/canvas') query.set('from', 'canvas');
  return '/create' + (query.size ? '?' + query.toString() : '');
}

export function toCreate(navigate: NavigateFunction, link: HandoffLink) {
  void navigate(createPath(link));
}

export function handoffOf(search: string): Handoff {
  const query = new URLSearchParams(search);
  const ref = query.get('ref');
  const slot = query.get('slot');
  return {
    rerun: Number(query.get('rerun')) || null,
    reuseSeed: query.get('seed') === 'reuse',
    prefill:
      ref && slot
        ? {
            slot,
            ref: { comfy_name: ref, name: query.get('ref_name') || ref },
            parent: Number(query.get('parent')) || undefined,
          }
        : undefined,
    from: query.get('from') === 'canvas' ? '/canvas' : undefined,
  };
}
