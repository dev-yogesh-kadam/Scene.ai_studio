// The console's Jobs section: everyone's jobs by status, and the drawer of one.

import { useState } from 'react';
import { api } from '../../../common/api';
import { Segmented } from '../../../common/components/Segmented';
import { useFilters, useSection } from '../shared/context';
import { ExportLink, Loaded, Pager, Person, Pill, SearchBox, Table, ago, number, span } from '../shared/ui';
import { JobDrawer } from './JobDrawer';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from './Jobs.module.css';
import css3 from '../shared/Console.module.css';
const css = classesOf(css0, css1, css2, css3);

type Row = {
  id: string;
  name: string;
  workflow: string;
  user_name: string;
  user_email: string;
  status: string;
  clip: number;
  clips: number;
  step: number;
  steps: number;
  node: string;
  explained?: string;
  error?: string;
  summary?: string;
  started: number | null;
  finished: number | null;
  created: number;
  cost: number;
};

const detail = (j: Row) =>
  j.status === 'running'
    ? [j.clips > 1 && `clip ${j.clip}/${j.clips}`, j.steps ? `step ${j.step}/${j.steps}` : 'starting', j.node]
        .filter(Boolean)
        .join(' · ')
    : j.explained || j.error || j.summary;

export default function Jobs() {
  const [s, set] = useFilters<{ status: string; q: string; offset: number }>('jobs');
  const [open, setOpen] = useState<string | null>(null);
  const query = useSection('jobs', [s.status, s.q, s.offset], () =>
    api<{ jobs: Row[]; total: number }>(
      '/api/admin/jobs?' + new URLSearchParams({ status: s.status, q: s.q, offset: String(s.offset) }),
    ),
  );
  return (
    <Loaded query={query}>
      {(data) => (
        <>
          <div className={css('toolbar')}>
            <Segmented
              choices={[
                { id: 'active', label: 'Running and waiting' },
                { id: 'done', label: 'Done' },
                { id: 'failed', label: 'Failed' },
                { id: 'cancelled', label: 'Cancelled' },
                { id: '', label: 'All' },
              ]}
              current={s.status}
              onPick={(status) => set({ status, offset: 0 })}
            />
            <SearchBox placeholder="Search job, workflow or user" value={s.q} onChange={(q) => set({ q, offset: 0 })} />
            <span className="muted small" style={{ marginLeft: 'auto' }}>
              {`${number(data.total)} job${data.total === 1 ? '' : 's'}`}
            </span>
            <ExportLink name="jobs" />
          </div>
          <div className={css('card')}>
            <Table
              head={['Job', 'User', 'Status', 'Details', 'Waited', 'Render', 'Credits', 'Added']}
              rows={data.jobs.map((j) => [
                <div key="j">
                  {j.name}
                  <div className="muted small">{j.workflow}</div>
                </div>,
                <Person key="p" name={j.user_name} email={j.user_email} />,
                <Pill key="s" status={j.status} />,
                <span
                  key="d"
                  className={css((j.status === 'failed' ? 'error ' : '') + 'small clip-text')}
                  title={detail(j) || undefined}
                >
                  {detail(j)}
                </span>,
                j.started ? span(j.started - j.created) : '',
                j.finished && j.started ? span(j.finished - j.started) : '',
                String(j.cost),
                ago(j.created),
              ])}
              onRow={(i) => setOpen(data.jobs[i].id)}
              empty={s.status === 'active' ? 'Nothing is running or waiting.' : 'No jobs match.'}
            />
          </div>
          <Pager total={data.total} offset={s.offset} onOffset={(offset) => set({ offset })} />
          {open && <JobDrawer id={open} onClose={() => setOpen(null)} />}
        </>
      )}
    </Loaded>
  );
}
