// What a job's numbers mean for the person waiting on it.
import { timeLeft } from '@scene/shared/format';
import type { Job, JobsAnswer } from '@scene/shared/types/api';

export const isActive = (job: Job) => job.status === 'running' || job.status === 'queued';

/** How far along a running job is, 0 to 1, or null when there's nothing to go on yet. */
export function progress(job: Job, now = Date.now() / 1000): number | null {
  if (job.status === 'done') return 1;
  if (job.status !== 'running') return null;
  const stepShare = job.steps > 0 ? job.step / job.steps : null;
  if (job.clips > 1) {
    const doneClips = Math.max(0, job.clip - 1);
    return Math.min(0.99, (doneClips + (stepShare ?? 0)) / job.clips);
  }
  if (stepShare != null) return Math.min(0.99, stepShare);
  // No steps reported (some models don't): go by the time it was expected to take.
  if (job.started && job.est_seconds) return Math.min(0.95, (now - job.started) / job.est_seconds);
  return null;
}

/** The line under a job's name: what it's doing now, in words. */
export function statusLine(job: Job): string {
  switch (job.status) {
    case 'queued':
      if (job.position === 1) return 'Next in line';
      return job.position ? `#${job.position} in line` : 'Waiting in line';
    case 'running': {
      const parts: string[] = [];
      if (job.clips > 1) parts.push(`${Math.max(0, job.clip - 1)} of ${job.clips} clips done`);
      else if (job.steps > 0) parts.push(`Step ${job.step} of ${job.steps}`);
      else parts.push(job.node || 'Rendering');
      const left = timeLeft(job.eta_seconds);
      if (left) parts.push(left);
      return parts.join(' · ');
    }
    case 'done':
      return job.items.length > 1 ? `Ready · ${job.items.length} results` : 'Ready';
    case 'failed':
      return job.reason || 'Something went wrong';
    case 'cancelled':
      return 'Cancelled · credits given back';
    default:
      return job.status;
  }
}

/** Running first, then the line in order, then the rest newest first. */
export function sortJobs(jobs: Job[]) {
  const rank = (job: Job) => (job.status === 'running' ? 0 : job.status === 'queued' ? 1 : 2);
  return [...jobs].sort((a, b) => {
    const byRank = rank(a) - rank(b);
    if (byRank) return byRank;
    if (a.status === 'queued') return (a.position ?? 999) - (b.position ?? 999);
    return (b.finished ?? b.created) - (a.finished ?? a.created);
  });
}

// What the phone keeps of a job the live connection describes: the queue's own snapshot (backend mobile.JOB_FIELDS).
const FIELDS = [
  'id',
  'name',
  'workflow',
  'kind',
  'status',
  'created',
  'started',
  'finished',
  'est_seconds',
  'eta_seconds',
  'step',
  'steps',
  'node',
  'clip',
  'clips',
  'position',
  'reason',
  'cost',
  'project_id',
] as const;

type Heard = Record<string, unknown> & { id: string; settings?: { prompt?: unknown; workflow_title?: unknown } };

/** The jobs the live connection said, in the shape GET /api/mobile/jobs gives them. The items a finished job made are
 *  not in what it says: they are kept from the list fetched before, and `missing` says a finished job has none known
 *  yet, so the list is fetched again for them. */
export function fromLive(heard: Heard[], was: JobsAnswer): { answer: JobsAnswer; missing: boolean } {
  const known = new Map(was.jobs.map((job) => [job.id, job]));
  let missing = false;
  const jobs = heard.map((raw) => {
    const job = Object.fromEntries(FIELDS.filter((k) => k in raw).map((k) => [k, raw[k]])) as unknown as Job;
    const before = known.get(raw.id);
    job.prompt = String(raw.settings?.prompt ?? '').slice(0, 500);
    job.workflow_title = String(raw.settings?.workflow_title ?? '');
    job.items = before?.items ?? [];
    if (job.status === 'done' && !job.items.length) missing = true;
    return job;
  });
  return { answer: { ...was, jobs }, missing };
}

/** How often a screen asks for the jobs: never while the live line is up (it says every change), and while it is down
 *  every 4 s with something rendering (as the studio's web page does) or every 15 s with nothing. */
export const POLL_ACTIVE = 4_000;
export const POLL_IDLE = 15_000;
export const pollEvery = (live: boolean, active: boolean) => (live ? false : active ? POLL_ACTIVE : POLL_IDLE);
