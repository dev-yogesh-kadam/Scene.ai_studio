import { describe, expect, it } from 'vitest';
import { rowsOf } from './Checks';

const now = Date.now() / 1000;

describe('the checks card', () => {
  it('a row for each check: ok, or the problem in its words', () => {
    const rows = rowsOf({
      database: { online: true, seconds: 0.002, detail: '' },
      render: { online: false, url: 'http://render:8188', detail: '' },
      model: {
        mode: 'this_pc',
        online: true,
        detail: '',
        claude_version: '2.1.3',
        signed_in: true,
        account: 'owner@example.com',
        plan: 'pro',
        running: 1,
        limit: 3,
      },
      programs: { ffmpeg: { ready: true, detail: '' }, motion: { ready: false, detail: 'npm install in motion/' } },
      disk: { folder: 'C:/Scene/Outputs', free: 5, total: 100 },
      backup: {
        folder: 'E:/b',
        last: now - 3600,
        check: { ok: true, detail: 'restored', when: now },
        restore_test: null,
      },
      langfuse: { in_use: true, url: 'http://lf', backlog: 2, down_since: now - 60, last_error: 'refused' },
    });
    const by = Object.fromEntries(rows.map((r) => [r.name, r]));
    expect(by['Database'].state).toBe('ok');
    expect(by['Render server']).toMatchObject({ state: 'problem' });
    expect(String(by['Render server'].words)).toContain('http://render:8188');
    expect(by['Agent model']).toMatchObject({
      state: 'ok',
      words: 'Claude on this PC · Claude Code 2.1.3 · signed in as owner@example.com · Pro · 1 of 3 calls running',
    });
    expect(by['Motion pages (HyperFrames)']).toMatchObject({ state: 'problem', words: 'npm install in motion/' });
    expect(by['Disk'].state).toBe('problem'); // 5% free
    expect(by['Last backup'].state).toBe('ok');
    expect(by['Backup check'].state).toBe('ok');
    expect(by['Restore test']).toMatchObject({ state: 'off', words: 'Not run yet' });
    expect(by['Langfuse'].state).toBe('problem');
    expect(by['Content check']).toMatchObject({ state: 'off', words: 'Not checked' });
  });

  it('the content check fails open, and says so for an hour after it could not run', () => {
    const gates = ['continuity', 'shot variety'];
    const failing = rowsOf({
      creative: { content_check: { mode: 'warn', failed_at: now - 60, error: 'busy' }, gates },
    });
    expect(failing.find((r) => r.name === 'Content check')?.state).toBe('problem');
    expect(String(failing.find((r) => r.name === 'Content check')?.words)).toContain('fails open');
    const fine = rowsOf({ creative: { content_check: { mode: 'block', failed_at: now - 7200 }, gates } });
    expect(fine.find((r) => r.name === 'Content check')).toMatchObject({ state: 'ok' });
    expect(
      rowsOf({ creative: { content_check: { mode: 'off' } } }).find((r) => r.name === 'Content check')?.state,
    ).toBe('off');
    expect(String(fine.find((r) => r.name === 'Quality gates')?.words)).toContain('never blocks');
  });

  it('a check that is missing (the database was down, an older studio) says so, and nothing breaks', () => {
    const rows = rowsOf({ database: { online: false, detail: 'connection refused' }, langfuse: null });
    expect(rows.find((r) => r.name === 'Database')).toMatchObject({ state: 'problem', words: 'connection refused' });
    expect(rows.find((r) => r.name === 'Langfuse')).toMatchObject({ state: 'off', words: 'Not checked' });
    expect(rows.find((r) => r.name === 'Render server')?.state).toBe('off');
  });
});
