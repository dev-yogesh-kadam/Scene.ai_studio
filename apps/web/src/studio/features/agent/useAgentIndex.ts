// The agent's tabs in a project: the index kept on the "agent" board ({tabs, open, active}), the same shape as always.
// The single conversation kept before there were tabs becomes "Agent 1".

import { useCallback, useEffect, useRef, useState } from 'react';
import { deleteBoard } from '@scene/shared/api/agent';
import { getBoard, putBoard } from '@scene/shared/api/canvas';
import type { Run, Spent } from './types';

const MAX_TABS = 30; // conversations kept per project; the oldest closed one goes when there are more
const AGENT = 'AGT'; // a tab's id in links: the canvas's address shows the tab open (?agent=AGT...), to keep or send

export type TabRow = { id: string; name: string; created: number; updated: number; spent: Spent | null };
export type Index = { tabs: TabRow[]; open: string[]; active: string | null };

const newId = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 6);

const tabInAddress = () => {
  const named = new URLSearchParams(location.search).get('agent') || '';
  return named.startsWith(AGENT) ? named.slice(AGENT.length) : null;
};
function showInAddress(id: string) {
  const query = new URLSearchParams(location.search);
  if (query.get('agent') === AGENT + id) return;
  query.set('agent', AGENT + id);
  history.replaceState(history.state, '', location.pathname + '?' + query);
}

type Saved = Partial<Index> & { runs?: Run[] };

export function useAgentIndex(project: number) {
  const [index, setIndexState] = useState<Index>({ tabs: [], open: [], active: null });
  const [seen, setSeen] = useState<string[]>([]); // tabs shown at least once: their conversations are kept mounted
  const [loaded, setLoaded] = useState(false);
  const latest = useRef(index);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const save = useCallback(() => putBoard('agent', project || null, latest.current).catch(() => {}), [project]);
  const setIndex = useCallback(
    (next: Index) => {
      latest.current = next;
      setIndexState(next);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => void save(), 600);
    },
    [save],
  );

  const show = useCallback(
    (id: string, from: Index = latest.current) => {
      if (!from.tabs.some((t) => t.id === id)) return;
      setIndex({ ...from, open: from.open.includes(id) ? from.open : [...from.open, id], active: id });
      setSeen((was) => (was.includes(id) ? was : [...was, id]));
      showInAddress(id);
    },
    [setIndex],
  );

  useEffect(() => {
    let live = true;
    void (async () => {
      let saved: Saved = {};
      try {
        saved = (await getBoard<Saved>('agent', project || 0)).data || {};
      } catch {
        // starts empty
      }
      if (!live) return;
      let next: Index = {
        tabs: Array.isArray(saved.tabs) ? saved.tabs : [],
        open: Array.isArray(saved.open) ? saved.open : [],
        active: saved.active || null,
      };
      if (!next.tabs.length) {
        const first: TabRow = { id: newId(), name: 'Agent 1', created: Date.now(), updated: Date.now(), spent: null };
        if (Array.isArray(saved.runs) && saved.runs.length) {
          await putBoard('agent-' + first.id, project || null, { runs: saved.runs }).catch(() => {});
          first.updated = Math.max(...saved.runs.map((r) => r.at || 0), 0) || Date.now();
        }
        next = { tabs: [first], open: [first.id], active: first.id };
        latest.current = next;
        await save();
      }
      const known = (id: string | null) => !!id && next.tabs.some((t) => t.id === id);
      next = { ...next, open: next.open.filter(known) };
      if (!next.open.length) next = { ...next, open: [next.tabs[0].id] };
      const named = tabInAddress(); // a link to one tab (?agent=AGT...) opens on it
      show(known(named) ? (named as string) : known(next.active) ? (next.active as string) : next.open[0], next);
      setLoaded(true);
    })();
    return () => {
      live = false;
      clearTimeout(timer.current);
    };
  }, [project, save, show]);

  const addTab = useCallback(() => {
    const now = latest.current;
    const used = new Set(now.tabs.map((t) => t.name));
    let n = now.tabs.length + 1;
    while (used.has(`Agent ${n}`)) n += 1;
    const made: TabRow = { id: newId(), name: `Agent ${n}`, created: Date.now(), updated: Date.now(), spent: null };
    let tabs = [...now.tabs, made];
    // Past the limit, the oldest conversation that is not open goes.
    while (tabs.length > MAX_TABS) {
      const old = [...tabs]
        .filter((t) => !now.open.includes(t.id) && t.id !== made.id)
        .sort((a, b) => a.updated - b.updated)[0];
      if (!old) break;
      tabs = tabs.filter((t) => t.id !== old.id);
      void deleteBoard(`agent-${old.id}`, project || 0).catch(() => {});
    }
    show(made.id, { ...now, tabs });
  }, [project, show]);

  const close = useCallback(
    (id: string) => {
      const now = latest.current;
      const open = now.open.filter((o) => o !== id);
      if (!open.length) {
        latest.current = { ...now, open };
        return addTab(); // there is always a conversation to type into
      }
      if (now.active === id) show(open[open.length - 1], { ...now, open });
      else setIndex({ ...now, open });
    },
    [addTab, setIndex, show],
  );

  const remove = useCallback(
    (id: string) => {
      const now = latest.current;
      const next = { ...now, tabs: now.tabs.filter((t) => t.id !== id), open: now.open.filter((o) => o !== id) };
      setSeen((was) => was.filter((x) => x !== id));
      void deleteBoard(`agent-${id}`, project || 0).catch(() => {});
      latest.current = next;
      if (!next.tabs.length || !next.open.length) return addTab();
      if (now.active === id) show(next.open[next.open.length - 1], next);
      else setIndex(next);
    },
    [addTab, project, setIndex, show],
  );

  const change = useCallback(
    (id: string, what: Partial<TabRow>) => {
      const now = latest.current;
      setIndex({ ...now, tabs: now.tabs.map((t) => (t.id === id ? { ...t, ...what } : t)) });
    },
    [setIndex],
  );

  const saved = useCallback(
    (id: string, { spent, updated }: { spent: Spent; updated: number | null }) => {
      const t = latest.current.tabs.find((x) => x.id === id);
      if (!t || (JSON.stringify(t.spent) === JSON.stringify(spent) && !updated)) return;
      change(id, { spent, ...(updated ? { updated } : {}) });
    },
    [change],
  );

  return { index, seen, loaded, show, addTab, close, remove, change, saved };
}
