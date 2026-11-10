// The compare board: a full-screen board over the canvas for testing workflows against each other. On the left a test
// is set up; on the right a run is shown as a grid that fills in live. Earlier runs are kept and can be opened again.
// Admins only. See backend/scene/api/bulk.py.

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { bulkRun, bulkRuns, cellAgain, startBulk, stopRun, type BulkWorkflow, type Cell } from '@scene/shared/api/bulk';
import { ask, tell } from '../../../common/components/Dialog';
import { Icon } from '../../../common/components/Icon/Icon';
import { cx, mergeModules } from '../../../common/cx';
import { JOBS, useJobs } from '../../live';
import { Grid } from './Grid';
import { NEW_TEST, Setup, short, usable, type Test } from './Setup';
import s1 from './Compare.module.css';
import s2 from './Compare2.module.css';

const s = mergeModules(s1, s2);

const LIVE = 3000; // ms between looks at a run that is still being made

type Props = { first: string | null; project: number; onClose: () => void };

export function CompareBoard({ first, project, onClose }: Props) {
  const client = useQueryClient();
  const [run, setRun] = useState(first);
  const [view, setView] = useState<'setup' | 'grid'>(first ? 'grid' : 'setup');
  const [test, setTest] = useState<Test>(NEW_TEST);
  const [starting, setStarting] = useState(false);
  const [notice, setNotice] = useState('');
  const runs = useQuery({ queryKey: ['bulk', 'runs'], queryFn: bulkRuns });
  const grid = useQuery({
    queryKey: ['bulk', 'run', run],
    queryFn: () => bulkRun(run!),
    enabled: !!run,
    refetchInterval: (query) =>
      query.state.data?.cells.some((c) => c.status === 'queued' || c.status === 'running') ? LIVE : false,
  });
  const busy = !!grid.data?.cells.some((c) => c.status === 'queued');
  const going = !!grid.data?.cells.some((c) => c.status === 'queued' || c.status === 'running');

  // A job of the run that changes (finished, failed) shows at once, not on the next look.
  const jobs = useJobs();
  useEffect(() => {
    if (!going) return;
    const timer = setTimeout(() => void client.invalidateQueries({ queryKey: ['bulk', 'run', run] }), 400);
    return () => clearTimeout(timer);
  }, [jobs, going, run, client]);
  // finished: the earlier runs say so, and the Stop button goes
  useEffect(() => {
    if (run && grid.data && !going) void client.invalidateQueries({ queryKey: ['bulk', 'runs'] });
  }, [run, grid.data, going, client]);

  useEffect(() => {
    const escape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', escape);
    return () => document.removeEventListener('keydown', escape);
  }, [onClose]);

  const queued = () => void client.invalidateQueries({ queryKey: JOBS });
  const open = (id: string | null) => {
    setRun(id);
    setView(id ? 'grid' : 'setup');
  };
  const start = async (ready: BulkWorkflow[]) => {
    const form = new FormData();
    form.append('kind', test.kind);
    form.append('prompts', JSON.stringify(test.prompts.filter((p) => p.trim())));
    form.append('workflows', JSON.stringify(ready.filter((w) => usable(w, test.pictures.length)).map((w) => w.id)));
    form.append('quality', test.quality);
    form.append('takes', String(test.takes));
    form.append('same_seed', test.sameSeed ? '1' : '');
    form.append('project_id', project ? String(project) : '');
    if (test.kind === 'video') {
      form.append('resolution', String(test.resolution));
      form.append('orientation', test.orientation);
      form.append('duration', String(test.duration));
    }
    for (const file of test.pictures) form.append('picture', file);
    setStarting(true);
    setNotice('');
    try {
      const done = await startBulk(form);
      if (done.skipped.length)
        void tell(`Left out:\n${done.skipped.map((x) => `${short(x.title)}: ${x.why}`).join('\n')}`);
      queued();
      void client.invalidateQueries({ queryKey: ['bulk', 'runs'] });
      open(done.run);
    } catch (e) {
      setNotice((e as Error).message);
    }
    setStarting(false);
  };
  const stop = async () => {
    const sure = await ask({
      title: 'Cancel every render of this run that is still waiting?',
      message: 'The ones running finish.',
      confirm: 'Cancel them',
      cancel: 'Keep them',
      danger: true,
    });
    if (!sure || !run) return;
    try {
      await stopRun(run);
      queued();
      void client.invalidateQueries({ queryKey: ['bulk', 'run', run] });
    } catch (e) {
      void tell((e as Error).message);
    }
  };
  const again = async (cell: Cell) => {
    if (!run) return;
    try {
      await cellAgain(run, cell.job);
      queued();
      void client.invalidateQueries({ queryKey: ['bulk', 'run', run] });
    } catch (e) {
      void tell((e as Error).message);
    }
  };

  return createPortal(
    <div
      className={cx(s.board, view !== 'setup' && !!run && s['setup-hidden'])}
      role="dialog"
      aria-label="Compare board"
    >
      <header className={s['board-head']}>
        <button className={cx('btn small', s['board-back'])} onClick={onClose} title="Back to the canvas (Esc)">
          <Icon name="back" />
          Back to the canvas
        </button>
        <h2>Compare board</h2>
        <select
          className={s['board-runs']}
          aria-label="Earlier runs"
          value={run ?? ''}
          onChange={(e) => open(e.target.value || null)}
        >
          <option value="">New test</option>
          {(runs.data ?? []).map((r) => (
            <option key={r.run} value={r.run}>
              {`${new Date(r.created * 1000).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })} · ${r.cells} cells · ${r.prompt.slice(0, 50)}`}
            </option>
          ))}
        </select>
        {run && (
          <button className="btn small" onClick={() => open(null)}>
            + New test
          </button>
        )}
        {run && (
          <button className="btn small" onClick={() => setView(view === 'setup' ? 'grid' : 'setup')}>
            {view === 'setup' ? 'Hide the setup' : 'Show the setup'}
          </button>
        )}
        {busy && (
          <button className="btn small quiet danger" onClick={() => void stop()}>
            Stop the waiting renders
          </button>
        )}
        <span style={{ flex: 1 }} />
        <button className="icon-btn" aria-label="Close the board" title="Close" onClick={onClose}>
          ×
        </button>
      </header>
      <div className={s['board-body']}>
        <aside className={s['board-setup']}>
          <Setup
            test={test}
            set={(change) => setTest((was) => ({ ...was, ...change }))}
            starting={starting}
            notice={notice}
            onStart={(ready) => void start(ready)}
          />
        </aside>
        <section className={s['board-main']}>
          {grid.error ? (
            <p className="notice error">{grid.error.message}</p>
          ) : (
            <Grid
              grid={run ? (grid.data ?? null) : null}
              now={grid.dataUpdatedAt / 1000}
              onAgain={(c) => void again(c)}
            />
          )}
        </section>
      </div>
    </div>,
    document.body,
  );
}
