// Backups in the console's System section: dated copies of the studio's database, whether the newest reads back whole,
// and how to put one back.

import { useState } from 'react';
import { api } from '../../../common/api';
import { useConsole } from '../shared/context';
import { Table, ago, bytes, failed, stamp } from '../shared/ui';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../shared/Console.module.css';
import css3 from './Shared.module.css';
import css4 from '../../../studio/pages/create/CreatePage.module.css';
const css = classesOf(css0, css1, css2, css3, css4);

export type Backups = {
  on: boolean;
  keep: number;
  folder: string;
  storage: string;
  database_kind: string;
  check?: { ok: boolean; copy?: string; detail: string; when: number } | null;
  copies: { what: string; name: string; made: number; bytes: number }[];
};

const RESTORE: Record<string, (b: Backups) => string[]> = {
  sqlite: (b) => [
    'Stop the studio app (Ctrl+C in its window).',
    `Copy the scene_<date>.db you want from ${b.folder} over scene.db in ${b.storage}. Keep the old scene.db aside until you have checked.`,
    'Start the app again and sign in to check.',
  ],
  postgres: (b) => [
    'Stop the studio app (Ctrl+C in its window).',
    'In a Command Prompt, as the postgres account: pg_restore -h localhost -U postgres --clean --if-exists -d scene ' +
      b.folder +
      '\\scene_<date>.dump',
    'Start the app again and sign in to check. docs/database.md has the full steps.',
  ],
};

function Doing({
  path,
  idle,
  busy,
  className,
  disabled,
}: {
  path: string;
  idle: string;
  busy: string;
  className: string;
  disabled: boolean;
}) {
  const { refresh } = useConsole();
  const [working, setWorking] = useState(false);
  return (
    <button
      className={className}
      disabled={disabled || working}
      onClick={() => {
        setWorking(true);
        void api(path, { method: 'POST' })
          .then(refresh, failed)
          .finally(() => setWorking(false));
      }}
    >
      {working ? busy : idle}
    </button>
  );
}

export function BackupsCard({ b }: { b: Backups }) {
  const c = b.check;
  const databases = b.copies.filter((x) => x.what === 'database');
  return (
    <div className={css('card')}>
      <div className={css('card-head')}>
        <h2>Backups</h2>
        <span className={css('pill ' + (b.on ? 'done' : 'failed'))}>{b.on ? 'On' : 'Off'}</span>
        <Doing
          path="/api/admin/backups"
          idle="Back up now"
          busy="Backing up…"
          className="btn small primary"
          disabled={!b.on}
        />
      </div>
      <p className="muted small">
        A backup is a dated copy of the studio&apos;s database: the accounts, projects, canvases, jobs, credits, prices
        and settings. With it goes a copy of config.json, which holds the server addresses and keys. The finished
        pictures, videos and sounds and NeuralCore&apos;s uploads are copied too, into the files folder beside them:
        only what is new or changed each time, and a file deleted in the studio keeps its copy there.
      </p>
      <p className="muted small">
        {b.on
          ? `A copy is made each time the app starts and once a day while it runs. The last ${b.keep} days are kept in ${b.folder}. A copy made today replaces today's earlier one.`
          : 'Backups are switched off on this installation (backup_keep is 0 in config.json).'}
      </p>
      <div
        className={'notice ' + (!c ? '' : c.ok ? 'ok' : 'error')}
        style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}
      >
        <span style={{ flex: 1, minWidth: 200 }}>
          {!c
            ? 'The newest copy has not been read back yet. It is checked once a day.'
            : `${c.ok ? 'Whole' : 'Not whole'}: ${c.copy || ''} ${c.detail} Checked ${ago(c.when)}.`}
        </span>
        <Doing
          path="/api/admin/backups/check"
          idle="Check the newest copy"
          busy="Checking…"
          className="btn small"
          disabled={!b.copies.length}
        />
      </div>
      <h3>{databases.length ? `Copies (${databases.length})` : 'Copies'}</h3>
      {databases.length ? (
        <Table
          head={['Copy', 'Made', 'Size']}
          rows={databases.slice(0, 14).map((x) => [x.name, stamp(x.made), bytes(x.bytes)])}
        />
      ) : (
        <p className="muted">No copies yet.</p>
      )}
      <h3>To put a copy back</h3>
      <ol className={css('steps')}>
        {(RESTORE[b.database_kind] || RESTORE.sqlite)(b).map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
      <p className="muted small">
        Everything done in the studio after that copy was made is lost, so restore only when the database is damaged or
        lost.
      </p>
    </div>
  );
}
