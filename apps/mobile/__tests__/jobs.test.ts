import { fromLive, isActive, pollEvery, progress, sortJobs, statusLine } from '@/lib/jobs';
import type { Job } from '@scene/shared/types/api';

const job = (over: Partial<Job>): Job => ({
  id: 'j',
  name: 'Fox',
  workflow: 'video/x',
  kind: 'video',
  status: 'queued',
  created: 1000,
  started: null,
  finished: null,
  est_seconds: null,
  eta_seconds: null,
  step: 0,
  steps: 0,
  node: '',
  clip: 0,
  clips: 0,
  position: null,
  cost: 0,
  project_id: null,
  prompt: '',
  workflow_title: '',
  items: [],
  ...over,
});

describe('progress', () => {
  it('counts finished clips of a chain', () => {
    expect(progress(job({ status: 'running', clip: 3, clips: 5, step: 0, steps: 10 }))).toBeCloseTo(2 / 5);
    expect(progress(job({ status: 'running', clip: 3, clips: 5, step: 5, steps: 10 }))).toBeCloseTo(2.5 / 5);
  });
  it('uses the steps of a single render, and the clock when there are none', () => {
    expect(progress(job({ status: 'running', step: 3, steps: 4 }))).toBeCloseTo(0.75);
    expect(progress(job({ status: 'running', started: 100, est_seconds: 100 }), 150)).toBeCloseTo(0.5);
    expect(progress(job({ status: 'running' }))).toBeNull();
  });
  it('never claims done before it is', () => {
    expect(progress(job({ status: 'running', step: 10, steps: 10 }))).toBeLessThan(1);
    expect(progress(job({ status: 'done' }))).toBe(1);
    expect(progress(job({ status: 'queued' }))).toBeNull();
  });
});

describe('statusLine', () => {
  it('says what a job is doing', () => {
    expect(statusLine(job({ status: 'queued', position: 1 }))).toBe('Next in line');
    expect(statusLine(job({ status: 'queued', position: 3 }))).toBe('#3 in line');
    expect(statusLine(job({ status: 'queued', waiting_for_server: true }))).toMatch(/render server/);
    expect(statusLine(job({ status: 'running', clip: 2, clips: 5, eta_seconds: 120 }))).toBe('1 of 5 clips done · about 2 min left');
    expect(statusLine(job({ status: 'failed', reason: 'Out of memory' }))).toBe('Out of memory');
    expect(statusLine(job({ status: 'done', items: [{ id: 1, kind: 'video' }, { id: 2, kind: 'video' }] }))).toBe('Ready · 2 results');
  });
});

describe('sortJobs', () => {
  it('puts running first, then the line in order, then the rest newest first', () => {
    const sorted = sortJobs([
      job({ id: 'old', status: 'done', finished: 10 }),
      job({ id: 'q2', status: 'queued', position: 2 }),
      job({ id: 'run', status: 'running' }),
      job({ id: 'new', status: 'failed', finished: 20 }),
      job({ id: 'q1', status: 'queued', position: 1 }),
    ]);
    expect(sorted.map((j) => j.id)).toEqual(['run', 'q1', 'q2', 'new', 'old']);
    expect(sorted.filter(isActive)).toHaveLength(3);
  });
});

describe('fromLive', () => {
  const said = (over: Record<string, unknown>) => {
    const { prompt, ...rest } = job(over);
    return { ...rest, settings: { prompt: prompt || 'A fox in snow', workflow_title: 'FLUX.2' }, values: { x: 1 } };
  };

  it('puts what the live connection says in the shape the phone lists, keeping the items fetched before', () => {
    const was = { jobs: [job({ id: 'a', status: 'done', items: [{ id: 7, kind: 'image' as const }] })], paused: true };
    const { answer, missing } = fromLive([said({ id: 'a', status: 'done' }), said({ id: 'b', status: 'running' })], was);
    expect(answer.paused).toBe(true);
    expect(answer.jobs[0].items).toEqual([{ id: 7, kind: 'image' }]);
    expect(answer.jobs[1]).toMatchObject({ id: 'b', status: 'running', prompt: 'A fox in snow', workflow_title: 'FLUX.2' });
    expect(answer.jobs[1]).not.toHaveProperty('settings');
    expect(missing).toBe(false);
  });

  it('says when a job finished and its items are not known yet', () => {
    const was = { jobs: [job({ id: 'a', status: 'running' })], paused: false };
    expect(fromLive([said({ id: 'a', status: 'done' })], was).missing).toBe(true);
  });
});

describe('pollEvery', () => {
  it('never polls while the live line is up, and slowly while it is down', () => {
    expect(pollEvery(true, true)).toBe(false);
    expect(pollEvery(false, true)).toBe(4_000);
    expect(pollEvery(false, false)).toBe(15_000);
  });
});
