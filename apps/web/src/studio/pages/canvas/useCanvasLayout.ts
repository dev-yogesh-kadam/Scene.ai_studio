// What the canvas shows and where: the project's items, NeuralCore entries and placed boards (TanStack Query, kept
// current by the live connection's "library changed"), the jobs, and the layout of the shots. The layout is the saved
// one (GET /api/boards/canvas) with the user's moves on it; arrange() puts everything new in its place. Nothing is
// placed before the saved layout is loaded.
//
// The layout is saved a moment after the last change. A change made just before the page is left, or the tab is
// closed, is saved at once then (keepalive lets it finish after the page is gone); a save that fails is tried once more
// instead of being lost quietly.

import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { canvasItems, getBoard, placement, putBoard } from '@scene/shared/api/canvas';
import { kit } from '@scene/shared/api/studio';
import type { Item } from '../../../common/media/item';
import { useJobs } from '../../live';
import { arrange, type CanvasJob } from './arrange';
import { readLayout, type KitEntry, type Layout, type Placed } from './geometry';

const SAVE_AFTER = 400;

export const canvasKeys = {
  items: (project: number) => ['library', 'canvas', project] as const,
  placed: (project: number) => ['library', 'placement', project] as const,
  board: (project: number) => ['board', 'canvas', project] as const,
  kit: (project: number) => ['kit', project] as const,
};

/** Seconds since 1970, moving on every `ms`: what arrange() reads as "now" (failed frames go after a day). */
function useNow(ms: number) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now() / 1000), ms);
    return () => clearInterval(timer);
  }, [ms]);
  return now;
}

export function useCanvasItems(project: number) {
  const items = useQuery({
    queryKey: canvasKeys.items(project),
    queryFn: () => canvasItems<Item>(project).then((found) => found.items),
  });
  const entries = useQuery({
    queryKey: canvasKeys.kit(project),
    queryFn: () => (project ? kit(project).then((found) => found.entries as KitEntry[]) : []),
  });
  const placed = useQuery({
    queryKey: canvasKeys.placed(project),
    queryFn: () =>
      placement<Placed['boards'][number]>(project).then(
        (found): Placed => ({ boards: Array.isArray(found.boards) ? found.boards : [] }),
        (): Placed => ({ boards: [] }),
      ),
  });
  return { items: items.data, entries: entries.data ?? [], placed: placed.data, error: items.error };
}

export function useCanvasLayout(project: number) {
  const { items, entries, placed, error } = useCanvasItems(project);
  const jobs = useJobs() as CanvasJob[];
  const board = useQuery({
    queryKey: canvasKeys.board(project),
    queryFn: () => getBoard<Layout>('canvas', project),
    staleTime: Infinity,
    gcTime: 0, // read again every time the canvas opens: another tab may have moved things
  });
  const [edited, setEdited] = useState<Layout | null>(null);
  const now = useNow(15_000);
  const loaded = useMemo(() => (board.data ? readLayout(board.data.data) : null), [board.data]);
  const base = edited ?? loaded;
  const arranged = useMemo(
    () => (base && items && placed ? arrange({ layout: base, items, jobs, entries, placed, project, now }) : null),
    [base, items, jobs, entries, placed, project, now],
  );

  // Saving: the newest layout waits here until it is sent.
  const unsaved = useRef<Layout | null>(null);
  const sent = useRef('');
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const send = useCallback(
    (data: Layout, keepalive = false) => {
      const put = (alive: boolean) => putBoard('canvas', project || null, data, alive);
      put(keepalive).catch(() => setTimeout(() => void put(false).catch(() => {}), 2000)); // tried once more
    },
    [project],
  );
  const flush = useCallback(
    (keepalive = false) => {
      clearTimeout(timer.current);
      const data = unsaved.current;
      if (!data) return;
      unsaved.current = null;
      send(data, keepalive);
    },
    [send],
  );
  const json = arranged ? JSON.stringify(arranged.layout) : '';
  useEffect(() => {
    if (!arranged) return;
    // the layout as it was loaded: saved only when placing or a move changed it
    if (!sent.current) sent.current = JSON.stringify(loaded);
    if (json === sent.current) return;
    sent.current = json;
    unsaved.current = arranged.layout;
    clearTimeout(timer.current);
    timer.current = setTimeout(() => flush(), SAVE_AFTER);
  }, [json, arranged, loaded, flush]);
  useEffect(() => {
    const onHide = () => flush(true);
    window.addEventListener('pagehide', onHide);
    return () => {
      window.removeEventListener('pagehide', onHide);
      flush(true); // a move made just before leaving is kept
    };
  }, [flush]);

  /** Change the layout (a move, a take put on top, a shot named). */
  const change = useCallback((next: Layout) => setEdited(next), []);

  return {
    arranged,
    items: items ?? [],
    entries,
    jobs,
    change,
    error: error ?? board.error,
  };
}
