// What the live connection says, kept only where it changed: a list of jobs (or plans) heard again keeps the objects
// that are the same as before, and the very same list when nothing changed, so a page drawn from it is not drawn again
// for a message that changed nothing it shows. And messages that come close together are put in at once (batch).

type Keyed = { id: string | number };

const same = (a: unknown, b: unknown) => a === b || JSON.stringify(a) === JSON.stringify(b);

/** `next` with every element equal to one of `was` replaced by that one; `was` itself when nothing changed. */
export function mergeList<T extends Keyed>(was: readonly T[] | undefined, next: readonly T[]): T[] {
  if (!was) return [...next];
  const old = new Map(was.map((item) => [item.id, item]));
  let changed = was.length !== next.length;
  const merged = next.map((item, at) => {
    const before = old.get(item.id);
    const kept = before && same(before, item) ? before : item;
    if (kept !== was[at]) changed = true;
    return kept;
  });
  return changed ? merged : (was as T[]);
}

/** The map of plans by id with those heard put in; the same map when none of them changed. */
export function mergeById<T extends Keyed>(was: ReadonlyMap<T['id'], T> | undefined, heard: readonly T[]) {
  const changed = heard.filter((item) => !was?.has(item.id) || !same(was.get(item.id), item));
  if (was && !changed.length) return was as Map<T['id'], T>;
  const next = new Map(was);
  for (const item of changed) next.set(item.id, item);
  return next;
}

/** Runs `apply` once for all the calls made before the next frame is drawn (or within `most` ms in a hidden tab,
 *  where frames are not drawn): each call says what it adds to the batch. `drop` forgets what is waiting. */
export function batcher<T>(apply: (batch: T[]) => void, most = 250) {
  let queued: T[] = [];
  let frame = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;
  const drop = () => {
    if (frame) cancelAnimationFrame(frame);
    if (timer) clearTimeout(timer);
    frame = 0;
    timer = null;
    const batch = queued;
    queued = [];
    return batch;
  };
  const flush = () => {
    const batch = drop();
    if (batch.length) apply(batch);
  };
  const add = (item: T) => {
    queued.push(item);
    if (frame || timer) return;
    if (typeof requestAnimationFrame === 'function') frame = requestAnimationFrame(flush);
    timer = setTimeout(flush, most);
  };
  return { add, flush, drop };
}
