// The list of queue rows, on the Create page.

import { useQueryClient } from '@tanstack/react-query';
import type { Job } from '@scene/shared/types/api';
import { api } from '../../../common/api';
import { tell } from '../../../common/components/Dialog';
import { creditsText, duration } from '../../../common/format';
import { JOBS } from '../../live';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../../../console/sections/shared/Console.module.css';
import css3 from '../../pages/projects/ProjectsPage.module.css';
const css = classesOf(css0, css1, css2, css3);

const STATUS: Record<string, string> = {
  queued: 'Waiting',
  running: 'Running',
  done: 'Done',
  failed: 'Failed',
  cancelled: 'Cancelled',
};

type Row = Job & { error?: string; summary?: string };

export function JobList({ jobs, limit }: { jobs: Row[]; limit?: number }) {
  const client = useQueryClient();
  const shown = limit ? jobs.slice(0, limit) : jobs;
  if (!shown.length) return <div className={css('empty')}>Nothing in the queue.</div>;
  const remove = (job: Row) =>
    api('/api/jobs/' + job.id, { method: 'DELETE' }).then(
      () => client.invalidateQueries({ queryKey: JOBS }),
      (e: Error) => tell(e.message),
    );
  return (
    <div role="list" aria-label="Jobs">
      {shown.map((job) => {
        const active = job.status === 'queued' || job.status === 'running';
        let detail = [job.error, job.cost > 0 && job.status !== 'done' && 'credits refunded']
          .filter(Boolean)
          .join(' · ');
        if (job.status === 'running') {
          detail = [
            job.clips > 1 && `Clip ${job.clip} of ${job.clips}`,
            job.steps ? `Step ${job.step} of ${job.steps}` : 'Starting…',
            job.node,
            job.eta_seconds != null && `about ${duration(job.eta_seconds)} left`,
          ]
            .filter(Boolean)
            .join(' · ');
        } else if (job.status === 'queued') {
          detail = [
            `Position ${job.position} in the queue`,
            job.est_seconds && `estimated ${duration(job.est_seconds)}`,
          ]
            .filter(Boolean)
            .join(' · ');
        } else if (job.status === 'done') {
          detail =
            `Finished in ${duration((job.finished ?? 0) - (job.started ?? 0))}` +
            (job.cost ? ` · ${creditsText(job.cost)}` : '');
        }
        const share = job.steps ? (Math.max(job.clip, 1) - 1 + job.step / job.steps) / Math.max(job.clips, 1) : 0;
        return (
          <div key={job.id} className={css('job')} role="listitem" aria-label={job.name}>
            <div className={css('job-head')}>
              <span className={css('name')}>{job.name}</span>
              <span className={css('pill ' + job.status)}>{STATUS[job.status]}</span>
              <button className="btn small quiet" onClick={() => void remove(job)}>
                {active ? 'Cancel' : 'Remove'}
              </button>
            </div>
            <div className={css('sub')}>
              {[job.workflow.split('/')[1].replace(/_/g, ' '), job.summary].filter(Boolean).join(' · ')}
            </div>
            {job.status === 'running' && (
              <div className={css('bar' + (job.steps ? '' : ' busy'))}>
                <div style={job.steps ? { width: `${Math.round(100 * share)}%` } : undefined} />
              </div>
            )}
            <div className={css('sub' + (job.status === 'failed' ? ' error' : ''))}>{detail}</div>
          </div>
        );
      })}
    </div>
  );
}
