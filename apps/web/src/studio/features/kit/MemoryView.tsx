// What the NeuralCore tab shows: for this module, the cast, the assets and the notes as folders; for "You", what the
// agent remembers of the user in every project, each of which can go.

import { useState, type ReactNode } from 'react';
import type { CastEntry, Memory, MemoryLeaf } from '@scene/shared/api/kit';
import { Icon } from '../../../common/components/Icon/Icon';
import { cx, mergeModules } from '../../../common/cx';
import { CastRows } from './CastRows';
import {
  Card,
  Folder,
  GridRow,
  RecordCard,
  isNode,
  jsonOf,
  kilobytes,
  latest,
  natural,
  partsOf,
  treeOf,
  type TreeState,
} from './MemoryTree';
import s1 from './Kit.module.css';
import s2 from './Kit2.module.css';

const s = mergeModules(s1, s2);

const ASSETS_PAGE = 60; // records of the catalogue shown at first, and how many more each time

type CastProps = {
  shown: CastEntry[];
  tools: ReactNode;
  onChange: (entry: CastEntry, json: Partial<CastEntry>) => void;
  onRemove: (entry: CastEntry) => void;
  onCard: (entry: CastEntry) => void;
  onMove: (entry: CastEntry, before: CastEntry | null) => void;
};

export function ModuleMemory({
  project,
  memory,
  error,
  entries,
  cast,
  onEdit,
}: {
  project: number;
  memory: Memory | undefined;
  error: string | undefined;
  entries: CastEntry[] | undefined;
  cast: CastProps;
  onEdit: (leaf: MemoryLeaf) => void;
}) {
  const [open, setOpen] = useState(() => new Set(['cast'])); // the folders and cards open now, by path
  const [long, setLong] = useState(() => new Set<string>()); // the long values shown whole
  const [assetsShown, setAssetsShown] = useState(ASSETS_PAGE);
  if (!project)
    return (
      <div className={s['kit-empty']}>
        <p>
          Memory belongs to a module. Open a project, or one of its modules, and what the agent keeps for it shows here.
        </p>
      </div>
    );
  if (error) return <p className="error small">{error}</p>;
  if (!memory) return <p className="small muted">Loading…</p>;
  const tree: TreeState = {
    open,
    toggle: (path) =>
      setOpen((was) => {
        const next = new Set(was);
        if (!next.delete(path)) next.add(path);
        return next;
      }),
    long,
    more: (path) => setLong((was) => new Set(was).add(path)),
    known: new Map((memory.assets?.records ?? []).map((r) => [r.id, r])),
    writable: !!memory.writable,
    edit: onEdit,
  };
  const notes = treeOf(memory.leaves);
  const all = entries ?? [];
  const records = memory.assets.records;
  return (
    <>
      <p className={cx('small muted', s['memory-lead'])}>
        What this module keeps: every agent tab of it and everyone in the project reads the same memory. Other modules
        keep their own.
      </p>
      <Folder
        name="cast"
        count={all.length}
        size={memory.cast ? kilobytes(memory.cast) : ''}
        when={0}
        raw={memory.cast}
        tree={tree}
      >
        {() => (
          <div className={s['mem-inner']}>
            <p className="small muted">
              This module&apos;s characters, places and props; other modules have their own. Always on goes into every
              shot that has a place for it.
            </p>
            {cast.tools}
            {!entries && <p className="small muted">Loading…</p>}
            {entries && !all.length && (
              <p className="small muted">
                Nothing yet. Add a character, a place or a prop with Add, or name one in a message to the agent:
                &quot;Maya - @1&quot;.
              </p>
            )}
            <CastRows
              entries={all}
              shown={cast.shown}
              onChange={cast.onChange}
              onRemove={cast.onRemove}
              onCard={cast.onCard}
              onMove={cast.onMove}
            />
            {all.length > 0 && !cast.shown.length && <p className="small muted">Nothing matches.</p>}
          </div>
        )}
      </Folder>
      <Folder
        name="assets"
        count={memory.assets.total}
        size={kilobytes(records)}
        when={records.length ? Date.parse(String(records[0].made)) / 1000 : 0}
        raw={records}
        tree={tree}
      >
        {() => (
          <div className={s['mem-inner']}>
            {!records.length && <p className="small muted">Nothing made or brought into this module yet.</p>}
            {records.slice(0, assetsShown).map((r) => (
              <RecordCard key={r.id} record={r} tree={tree} />
            ))}
            {records.length > assetsShown && (
              <button className="btn small" onClick={() => setAssetsShown((n) => n + ASSETS_PAGE)}>
                {`Show more (${records.length - assetsShown} left)`}
              </button>
            )}
          </div>
        )}
      </Folder>
      {[...notes.kids.entries()].sort(natural).map(([name, child]) => {
        const parts = partsOf(child) || [];
        const json = jsonOf(child);
        return (
          <Folder
            key={name}
            name={name}
            count={parts.length}
            size={kilobytes(json)}
            when={latest(child)}
            raw={json}
            tree={tree}
          >
            {() => (
              <div className={s['mem-inner']}>
                {parts.length ? (
                  parts.map(([k, v]) => (
                    <Card
                      key={k}
                      name={k}
                      child={v}
                      path={`/${name}/${k}`}
                      owner={isNode(child) ? child.leaf : null}
                      tree={tree}
                    />
                  ))
                ) : (
                  <GridRow name={name} child={child} path={'/' + name} owner={null} tree={tree} />
                )}
              </div>
            )}
          </Folder>
        );
      })}
      {!notes.kids.size && (
        <p className="small muted">No notes yet. The agent writes its plan, decisions and progress here as it works.</p>
      )}
    </>
  );
}

/** What the agent remembers of the user across all their projects (preferences, what they keep using). */
export function YouView({
  found,
  error,
  onForget,
}: {
  found: { entries: { key: string; value: string }[] } | undefined;
  error: string | undefined;
  onForget: (key: string) => void;
}) {
  if (error) return <p className="error small">{error}</p>;
  if (!found) return <p className="small muted">Loading…</p>;
  return (
    <>
      <p className={cx('small muted', s['memory-lead'])}>
        What the agent remembers of you in this module: how you like to work here and what you keep using. Other
        modules keep their own. It never overrides what you ask.
      </p>
      {found.entries.length ? (
        <div className={s['mem-inner']}>
          {found.entries.map((entry) => (
            <div key={entry.key} className={s['mem-card']}>
              <div className={s['mem-card-head']}>
                <div className={s['mem-card-text']}>
                  <b>{entry.key}</b>
                  <div className={s['mem-summary']}>{entry.value}</div>
                </div>
                <span className={s['mem-acts']}>
                  <button
                    className={cx('icon-btn', s['mem-act'])}
                    title="Forget it"
                    aria-label={`Forget ${entry.key}`}
                    onClick={() => onForget(entry.key)}
                  >
                    <Icon name="trash" />
                  </button>
                </span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="small muted">
          Nothing yet. Tell the agent how you like to work (&quot;I always make Reels&quot;) and it keeps it.
        </p>
      )}
    </>
  );
}
