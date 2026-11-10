// The shell's one polite live region (U2): what changed in the user's work, said by a screen reader without moving the
// focus: "Image ready: Fox", "Render failed, credits refunded", "Plan finished". It listens to the jobs and the plans
// the live connection puts in the Query cache and says only a change of state, never the progress in between.

import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import type { Job } from '@scene/shared/types/api';
import { JOBS, PLANS } from '../live';
import s from './Announcer.module.css';

const KIND: Record<string, string> = { image: 'Image', video: 'Video', audio: 'Sound' };

/** What to say about the jobs that changed since `was` (id → status), and nothing for those first seen. */
export function saidOfJobs(was: Map<string, string>, jobs: Job[]) {
  const said: string[] = [];
  for (const job of jobs) {
    const before = was.get(job.id);
    if (!before || before === job.status) continue;
    if (job.status === 'done') said.push(`${KIND[job.kind] ?? 'Result'} ready: ${job.name}`);
    if (job.status === 'failed')
      said.push(job.cost ? `Render failed, credits refunded: ${job.name}` : `Render failed: ${job.name}`);
  }
  return said;
}

export function Announcer() {
  const client = useQueryClient();
  const [text, setText] = useState('');
  useEffect(() => {
    const jobs = new Map<string, string>();
    const plans = new Map<number, string>();
    const remember = () => {
      for (const job of client.getQueryData<Job[]>(JOBS) ?? []) jobs.set(job.id, job.status);
      for (const [id, plan] of client.getQueryData<Map<number, { state: string }>>(PLANS) ?? [])
        plans.set(id, plan.state);
    };
    remember(); // what was already so when the page opened is not news
    return client.getQueryCache().subscribe((event) => {
      if (event.type !== 'updated') return;
      const key = event.query.queryKey[0];
      const said: string[] = [];
      if (key === JOBS[0]) said.push(...saidOfJobs(jobs, client.getQueryData<Job[]>(JOBS) ?? []));
      if (key === PLANS[0])
        for (const [id, plan] of client.getQueryData<Map<number, { state: string }>>(PLANS) ?? []) {
          const before = plans.get(id);
          if (before && before !== plan.state && plan.state === 'done') said.push('Plan finished');
          if (before && before !== plan.state && plan.state === 'failed') said.push('Plan stopped: a step failed');
        }
      remember();
      if (said.length) setText(said.join('. '));
    });
  }, [client]);
  // A new text replaces the last; the region itself stays, so the reader hears each change.
  return (
    <div className={s.said} aria-live="polite" aria-atomic="true">
      {text}
    </div>
  );
}
