import { describe, expect, it } from 'vitest';
import type { Job } from '@scene/shared/types/api';
import { saidOfJobs } from './Announcer';

const job = (id: string, status: string, extra: Partial<Job> = {}) =>
  ({ id, status, kind: 'image', name: id, cost: 40, ...extra }) as Job;

describe('the live region says what changed', () => {
  it('a finished picture, a failed render with its credits back, and nothing for progress', () => {
    const was = new Map([
      ['a', 'running'],
      ['b', 'running'],
      ['c', 'queued'],
    ]);
    expect(saidOfJobs(was, [job('a', 'done'), job('b', 'failed'), job('c', 'running')])).toEqual([
      'Image ready: a',
      'Render failed, credits refunded: b',
    ]);
  });

  it('a clip, a free render that failed, and a job seen for the first time says nothing', () => {
    const was = new Map([
      ['v', 'running'],
      ['f', 'running'],
    ]);
    expect(
      saidOfJobs(was, [job('v', 'done', { kind: 'video' }), job('f', 'failed', { cost: 0 }), job('n', 'done')]),
    ).toEqual(['Video ready: v', 'Render failed: f']);
  });
});
