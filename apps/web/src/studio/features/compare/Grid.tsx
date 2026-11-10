// The right side of the compare board: a run as a grid, prompts down the side and workflows across the top, each cell
// filling in live with what it made, how long it took, or why it failed. A cell opens big (arrows walk along the row);
// the best of a row can be starred (the item's own rating, so every browser sees it); each column says how its
// workflow did.

import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { rateItem } from '@scene/shared/api/agent';
import type { Cell, Grid as GridData } from '@scene/shared/api/bulk';
import { Icon } from '../../../common/components/Icon/Icon';
import { Still } from '../../../common/components/Still';
import { cx, mergeModules } from '../../../common/cx';
import { prefs } from '../../../common/prefs';
import { short } from './Setup';
import s1 from './Compare.module.css';
import s2 from './Compare2.module.css';

const s = mergeModules(s1, s2);

export const clock = (sec: number | null | undefined) =>
  sec == null
    ? ''
    : sec < 60
      ? `${sec.toFixed(1)} s`
      : `${Math.floor(sec / 60)} min ${String(Math.round(sec % 60)).padStart(2, '0')} s`;

/** The starred cells: those whose item is rated 1. A star given or taken shows at once and is saved on the item. */
function useStars(grid: GridData | null) {
  const client = useQueryClient();
  const key = ['bulk', 'run', grid?.run ?? ''];
  const stars = new Set((grid?.cells ?? []).filter((c) => (c.items[0]?.rating ?? 0) > 0).map((c) => c.job));
  const rate = (jobs: Map<string, number>) =>
    client.setQueryData<GridData>(
      key,
      (was) =>
        was && {
          ...was,
          cells: was.cells.map((c) =>
            jobs.has(c.job) && c.items[0]
              ? { ...c, items: [{ ...c.items[0], rating: jobs.get(c.job) }, ...c.items.slice(1)] }
              : c,
          ),
        },
    );
  const toggle = (job: string) => {
    const item = grid?.cells.find((c) => c.job === job)?.items[0];
    if (!item) return;
    const rating = stars.has(job) ? 0 : 1;
    rate(new Map([[job, rating]]));
    rateItem(item.id, rating).catch(() => void client.invalidateQueries({ queryKey: key }));
  };
  // Stars this browser kept before they were the items' ratings: given to the items once, then forgotten here.
  const run = grid?.run ?? '';
  useEffect(() => {
    if (!run) return;
    let kept: unknown;
    try {
      kept = JSON.parse(prefs.get('scene.stars.' + run, '[]'));
    } catch {
      kept = [];
    }
    prefs.remove('scene.stars.' + run);
    const cells = client.getQueryData<GridData>(['bulk', 'run', run])?.cells ?? [];
    const jobs = Array.isArray(kept)
      ? cells.filter((c) => kept.includes(c.job) && c.items[0] && !c.items[0].rating)
      : [];
    if (!jobs.length) return;
    client.setQueryData<GridData>(
      ['bulk', 'run', run],
      (was) =>
        was && {
          ...was,
          cells: was.cells.map((c) =>
            jobs.includes(c) ? { ...c, items: [{ ...c.items[0], rating: 1 }, ...c.items.slice(1)] } : c,
          ),
        },
    );
    for (const c of jobs) void rateItem(c.items[0].id, 1).catch(() => {});
  }, [client, run]);
  return { stars, toggle };
}

export function Grid({ grid, now, onAgain }: { grid: GridData | null; now: number; onAgain: (cell: Cell) => void }) {
  const [big, setBig] = useState<{ row: number; job: string } | null>(null);
  const { stars, toggle } = useStars(grid);
  if (!grid)
    return (
      <div className={s['board-empty']}>
        <h3>Set up a test on the left</h3>
        <p className="muted">
          Write a prompt or a few, tick the workflows to compare, and run it. The board fills in as the renders finish:
          one row per prompt, one column per workflow.
        </p>
      </div>
    );
  const at = new Map<string, Cell[]>();
  for (const c of grid.cells) at.set(`${c.row}|${c.workflow}`, [...(at.get(`${c.row}|${c.workflow}`) || []), c]);
  const cols = grid.workflows;
  const made = grid.cells.filter((c) => c.status === 'done').length;
  const over = grid.cells.filter((c) => !['queued', 'running'].includes(c.status)).length;
  return (
    <>
      <div className={s['board-progress']}>
        <i style={{ width: `${((100 * over) / grid.cells.length).toFixed(1)}%` }} />
      </div>
      <p className={cx('muted small', s['board-status'])}>
        {`${made} of ${grid.cells.length} made` +
          (grid.cells.some((c) => c.status === 'running') ? ' · rendering' : '')}
      </p>
      <div className={s['board-scroll']}>
        <div
          className={s['board-table']}
          style={{ gridTemplateColumns: `minmax(180px, 240px) repeat(${cols.length}, minmax(200px, 1fr))` }}
        >
          <div className={s['board-corner']}>
            <b>{`${grid.prompts.length} × ${cols.length}${grid.takes > 1 ? ` × ${grid.takes}` : ''}`}</b>
            <span className="muted small">{grid.same_seed ? 'One seed per take' : 'Random seeds'}</span>
          </div>
          {cols.map((w) => (
            <div key={w.id} className={s['board-col']} title={w.title}>
              {short(w.title)}
            </div>
          ))}
          {grid.rows.map((row, i) => [
            <div key={'head' + row} className={s['board-rowhead']}>
              <b>{`Shot ${i + 1}`}</b>
              <p title={grid.prompts[i]}>{grid.prompts[i]}</p>
            </div>,
            ...cols.map((w) => (
              <CellBox
                key={row + '|' + w.id}
                takes={at.get(`${row}|${w.id}`) || []}
                many={grid.takes > 1}
                now={now}
                stars={stars}
                onStar={toggle}
                onAgain={onAgain}
                onOpen={(c) => setBig({ row: i, job: c.job })}
              />
            )),
          ])}
          {/* how each workflow did over the whole run */}
          <div className={cx(s['board-foothead'], 'muted small')}>Over the run</div>
          {cols.map((w) => {
            const mine = grid.cells.filter((c) => c.workflow === w.id);
            const done = mine.filter((c) => c.status === 'done');
            const times = done.map((c) => c.seconds).filter((x): x is number => x != null);
            const failed = mine.filter((c) => c.status === 'failed').length;
            const starred = mine.filter((c) => stars.has(c.job)).length;
            return (
              <div key={'foot' + w.id} className={s['board-foot']}>
                <span>{`${done.length} of ${mine.length} made`}</span>
                {times.length ? <span>{`avg ${clock(times.reduce((a, b) => a + b, 0) / times.length)}`}</span> : null}
                {failed ? <span className={s.bad}>{`${failed} failed`}</span> : null}
                {starred ? <span className={s['star-count']}>{`★ ${starred}`}</span> : null}
              </div>
            );
          })}
        </div>
      </div>
      {big && <Big grid={grid} rowIndex={big.row} job={big.job} onClose={() => setBig(null)} />}
    </>
  );
}

function CellBox({
  takes,
  many,
  now,
  stars,
  onStar,
  onAgain,
  onOpen,
}: {
  takes: Cell[];
  many: boolean;
  now: number; // when the run was last looked at, in seconds
  stars: Set<string>;
  onStar: (job: string) => void;
  onAgain: (cell: Cell) => void;
  onOpen: (cell: Cell) => void;
}) {
  if (!takes.length)
    return (
      <div className={s['board-cell']}>
        <div className={cx(s['board-blank'], 'muted small')}>Left out</div>
      </div>
    );
  return (
    <div className={s['board-cell']}>
      {[...takes]
        .sort((a, b) => a.take - b.take)
        .map((c) => {
          const item = c.items[0];
          const starred = stars.has(c.job);
          const shown = c.status === 'done' && item;
          return (
            <div key={c.job} className={s['board-take']}>
              <div
                className={cx(s['board-frame'], s[c.status])}
                tabIndex={shown ? 0 : undefined}
                onClick={shown ? () => onOpen(c) : undefined}
              >
                {shown ? (
                  <Still url={`/api/library/${item.id}/file`} kind={item.kind} name={item.name} />
                ) : c.status === 'failed' ? (
                  <div className={s['board-why']}>
                    <b>Failed</b>
                    <span>{c.error || 'Something went wrong.'}</span>
                  </div>
                ) : c.status === 'running' ? (
                  <div className={s['board-wait']}>
                    <span className={s['board-dot']} />
                    {clock(c.started ? now - c.started : 0)}
                  </div>
                ) : (
                  <div className={cx(s['board-wait'], 'muted')}>{c.status === 'cancelled' ? 'Stopped' : 'Waiting'}</div>
                )}
              </div>
              <div className={s['board-meta']}>
                <span>{many ? `Take ${c.take + 1}` : ''}</span>
                <span className="muted">{c.status === 'done' || c.status === 'failed' ? clock(c.seconds) : ''}</span>
                {c.status === 'done' && (
                  <button
                    className={cx(s.star, starred && s.on)}
                    title={starred ? 'Unstar' : 'Star the best'}
                    aria-pressed={starred}
                    onClick={() => onStar(c.job)}
                  >
                    {starred ? '★' : '☆'}
                  </button>
                )}
                {(c.status === 'failed' || c.status === 'done' || c.status === 'cancelled') && (
                  <button className={s.again} title="Make this cell again" onClick={() => onAgain(c)}>
                    <Icon name="retry" />
                  </button>
                )}
              </div>
            </div>
          );
        })}
    </div>
  );
}

/** One result big, with what made it; arrows walk along the row (the same prompt, the next workflow). */
function Big({ grid, rowIndex, job, onClose }: { grid: GridData; rowIndex: number; job: string; onClose: () => void }) {
  const row = grid.rows[rowIndex];
  const along = grid.workflows.flatMap((col) =>
    grid.cells
      .filter((x) => x.row === row && x.workflow === col.id && x.status === 'done' && x.items[0])
      .map((x) => ({ col, x })),
  );
  const [i, setI] = useState(() =>
    Math.max(
      0,
      along.findIndex((a) => a.x.job === job),
    ),
  );
  useEffect(() => {
    const keys = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      } else if (e.key === 'ArrowRight') setI((n) => (n + 1) % along.length);
      else if (e.key === 'ArrowLeft') setI((n) => (n - 1 + along.length) % along.length);
    };
    document.addEventListener('keydown', keys, true);
    return () => document.removeEventListener('keydown', keys, true);
  }, [along.length, onClose]);
  if (!along.length) return null;
  const { col, x } = along[i % along.length];
  const item = x.items[0];
  return (
    <div
      className={s['board-big']}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className={s['board-big-inner']}>
        <div className={s['board-big-media']}>
          {item.kind === 'video' ? (
            <video src={`/api/library/${item.id}/file`} controls autoPlay loop />
          ) : (
            <img src={`/api/library/${item.id}/file`} alt={item.name} />
          )}
        </div>
        <div className={s['board-big-facts']}>
          <b>{short(col.title)}</b>
          <span className="muted">
            {`Shot ${rowIndex + 1}${grid.takes > 1 ? ` · take ${x.take + 1}` : ''} · ${clock(x.seconds)}${x.seed ? ` · seed ${x.seed}` : ''}`}
          </span>
          <p>{grid.prompts[rowIndex]}</p>
          <span className="muted small">{`${(i % along.length) + 1} of ${along.length} in this row · ← → to move, Esc to close`}</span>
        </div>
      </div>
    </div>
  );
}
