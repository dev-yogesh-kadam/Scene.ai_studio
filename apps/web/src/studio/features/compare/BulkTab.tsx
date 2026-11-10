// Bulk generation, a tab of the canvas's side panel for admins: where the compare board opens, for a new test or one
// run before. Free.

import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { bulkRuns } from '@scene/shared/api/bulk';
import { CompareBoard } from './CompareBoard';
import s1 from './Compare.module.css';
import s2 from './Compare2.module.css';
import { mergeModules } from '../../../common/cx';

const s = mergeModules(s1, s2);

const when = (t: number) => new Date(t * 1000).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });

export function BulkTab({ project, active, focus }: { project: number; active: boolean; focus: number }) {
  const [board, setBoard] = useState<{ run: string | null } | null>(null);
  const first = useRef<HTMLButtonElement>(null);
  const runs = useQuery({ queryKey: ['bulk', 'runs'], queryFn: bulkRuns, enabled: active });
  useEffect(() => {
    if (focus && active) first.current?.focus();
  }, [focus, active]);
  const list = runs.data ?? [];
  return (
    <>
      <p className="muted small">
        Test and compare workflows: several prompts, many workflows, the same seed for all, on one board. Prompts are
        rows, workflows are columns. The results also come onto this canvas. Free. Admins only.
      </p>
      <button ref={first} className="btn primary block" onClick={() => setBoard({ run: null })}>
        Open the compare board
      </button>
      {list.length ? <h4 className={s['bulk-runs-head']}>Earlier runs</h4> : null}
      {list.slice(0, 12).map((r) => (
        <button key={r.run} className={s['bulk-run']} onClick={() => setBoard({ run: r.run })}>
          <span className={s['bulk-run-prompt']}>{r.prompt || 'No prompt'}</span>
          <span className="muted small">
            {`${when(r.created)} · ${r.cells} cells · ${r.done} made` +
              (r.failed ? ` · ${r.failed} failed` : '') +
              (r.queued || r.running ? ` · ${r.queued + r.running} to go` : '')}
          </span>
        </button>
      ))}
      {board && <CompareBoard first={board.run} project={project} onClose={() => setBoard(null)} />}
    </>
  );
}
