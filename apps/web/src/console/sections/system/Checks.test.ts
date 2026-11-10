import { describe, expect, it } from 'vitest';
import { rowsOf } from './Checks';

const now = Date.now() / 1000;

describe('the checks card', () => {
  it('a row for each check: ok, or the problem in its words', () => {
    const rows = rowsOf({
      database: { online: true, seconds: 0.002, detail: '' },
      render: { online: false, url: 'http://render:8188', detail: '' },
      model: { online: true, detail: '', signed_in: true, plan: 'Max' },
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
    expect(by['Agent model']).toMatchObject({ state: 'ok', words: 'Claude Code ready · signed in · Max' });
    expect(by['Motion pages (HyperFrames)']).toMatchObject({ state: 'problem', words: 'npm install in motion/' });
    expect(by['Disk'].state).toBe('problem'); // 5% free
    expect(by['Last backup'].state).toBe('ok');
    expect(by['Backup check'].state).toBe('ok');
    expect(by['Restore test']).toMatchObject({ state: 'off', words: 'Not run yet' });
    expect(by['Langfuse'].state).toBe('problem');
  });

  it('a check that is missing (the database was down, an older studio) says so, and nothing breaks', () => {
    const rows = rowsOf({ database: { online: false, detail: 'connection refused' }, langfuse: null });
    expect(rows.find((r) => r.name === 'Database')).toMatchObject({ state: 'problem', words: 'connection refused' });
    expect(rows.find((r) => r.name === 'Langfuse')).toMatchObject({ state: 'off', words: 'Not checked' });
    expect(rows.find((r) => r.name === 'Render server')?.state).toBe('off');
  });
});
