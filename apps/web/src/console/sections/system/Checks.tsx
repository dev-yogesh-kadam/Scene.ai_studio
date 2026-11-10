// The System section's checks card: every check the studio makes of itself (GET /api/admin/system's "checks",
// backend/scene/health.py checks()), one row each, ok or the problem in its words. A studio that sends no "checks"
// (an older backend) shows no card. Every field is read defensively: a check that is missing says "not checked".

import type { ReactNode } from 'react';
import { Table, ago, bytes } from '../shared/ui';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../shared/Console.module.css';
const css = classesOf(css0, css1, css2);

type Ready = { ready?: boolean; detail?: string };
type Outcome = { ok?: boolean; detail?: string; when?: number } | null;
export type Checks = {
  database?: { online?: boolean; seconds?: number; detail?: string };
  render?: { online?: boolean; url?: string; since?: number; detail?: string };
  model?: { online?: boolean; detail?: string; signed_in?: boolean | null; plan?: string };
  programs?: { ffmpeg?: Ready; motion?: Ready };
  disk?: { folder?: string; free?: number; total?: number };
  backup?: { folder?: string; last?: number | null; check?: Outcome; restore_test?: Outcome };
  langfuse?: {
    in_use?: boolean;
    url?: string;
    backlog?: number;
    down_since?: number | null;
    last_error?: string;
    owns_words?: boolean;
  } | null;
};

/** ok: fine; problem: something to act on; off: not set up or not checked (neither). */
type Row = { name: string; state: 'ok' | 'problem' | 'off'; words: ReactNode };

const DAY = 86400;
const outcome = (name: string, o: Outcome | undefined, never: string): Row =>
  !o
    ? { name, state: 'off', words: never }
    : {
        name,
        state: o.ok ? 'ok' : 'problem',
        words: [o.ok ? 'Passed' : 'Failed', o.when ? ago(o.when) : '', o.detail].filter(Boolean).join(' · '),
      };

export function rowsOf(c: Checks): Row[] {
  const rows: Row[] = [];
  const db = c.database;
  rows.push(
    !db
      ? { name: 'Database', state: 'off', words: 'Not checked' }
      : db.online
        ? { name: 'Database', state: 'ok', words: `Answers (${db.seconds ?? 0} s)` }
        : { name: 'Database', state: 'problem', words: db.detail || 'Does not answer' },
  );
  const r = c.render;
  rows.push(
    !r
      ? { name: 'Render server', state: 'off', words: 'Not checked' }
      : r.online
        ? { name: 'Render server', state: 'ok', words: `Online${r.url ? ' at ' + r.url : ''}` }
        : {
            name: 'Render server',
            state: 'problem',
            words: r.detail || `Not answering${r.url ? ' at ' + r.url : ''}${r.since ? ' since ' + ago(r.since) : ''}`,
          },
  );
  const m = c.model;
  rows.push(
    !m
      ? { name: 'Agent model', state: 'off', words: 'Not checked' }
      : m.online
        ? {
            name: 'Agent model',
            state: 'ok',
            words: ['Claude Code ready', m.signed_in ? 'signed in' : '', m.plan].filter(Boolean).join(' · '),
          }
        : { name: 'Agent model', state: 'problem', words: m.detail || 'Not ready' },
  );
  for (const [key, name] of [
    ['ffmpeg', 'ffmpeg (long videos)'],
    ['motion', 'Motion pages (HyperFrames)'],
  ] as const) {
    const p = c.programs?.[key];
    rows.push(
      !p
        ? { name, state: 'off', words: 'Not checked' }
        : { name, state: p.ready ? 'ok' : 'problem', words: p.ready ? 'Ready' : p.detail || 'Missing' },
    );
  }
  const d = c.disk;
  if (d && d.total) {
    const free = d.free ?? 0;
    rows.push({
      name: 'Disk',
      state: free / d.total < 0.1 ? 'problem' : 'ok',
      words: `${bytes(free)} free of ${bytes(d.total)}${d.folder ? ' · ' + d.folder : ''}`,
    });
  } else rows.push({ name: 'Disk', state: 'off', words: 'Not checked' });
  const b = c.backup;
  rows.push(
    !b
      ? { name: 'Last backup', state: 'off', words: 'Not checked' }
      : b.last
        ? {
            name: 'Last backup',
            state: Date.now() / 1000 - b.last > 2 * DAY ? 'problem' : 'ok',
            words: `${ago(b.last)}${b.folder ? ' · ' + b.folder : ''}`,
          }
        : { name: 'Last backup', state: 'problem', words: 'No copy yet' },
  );
  rows.push(outcome('Backup check', b?.check, 'Not run yet'));
  rows.push(outcome('Restore test', b?.restore_test, 'Not run yet'));
  const l = c.langfuse;
  rows.push(
    !l
      ? { name: 'Langfuse', state: 'off', words: 'Not checked' }
      : !l.in_use
        ? { name: 'Langfuse', state: 'off', words: 'Not set (Servers & APIs)' }
        : l.down_since
          ? {
              name: 'Langfuse',
              state: 'problem',
              words: `Not taking calls since ${ago(l.down_since)}${l.last_error ? ': ' + l.last_error : ''} · ${l.backlog ?? 0} waiting`,
            }
          : {
              name: 'Langfuse',
              state: 'ok',
              words: `Sending to ${l.url || 'Langfuse'} · ${l.backlog ?? 0} waiting${l.owns_words ? ' · keeps the words' : ''}`,
            },
  );
  return rows;
}

const PILL = { ok: 'done', problem: 'failed', off: 'cancelled' } as const;
const SAID = { ok: 'OK', problem: 'Problem', off: '—' } as const;

export function ChecksCard({ c }: { c: Checks }) {
  const rows = rowsOf(c);
  const wrong = rows.filter((r) => r.state === 'problem').length;
  return (
    <div className={css('card')}>
      <div className={css('card-head')}>
        <h2>Checks</h2>
        <span className={css('pill ' + (wrong ? 'failed' : 'done'))}>
          {wrong ? `${wrong} problem${wrong === 1 ? '' : 's'}` : 'All OK'}
        </span>
      </div>
      <Table
        head={['Check', '', 'What it found']}
        rows={rows.map((r) => [
          r.name,
          <span key="s" className={css('pill ' + PILL[r.state])}>
            {SAID[r.state]}
          </span>,
          <span key="w" className={r.state === 'problem' ? undefined : 'muted'}>
            {r.words}
          </span>,
        ])}
      />
    </div>
  );
}
