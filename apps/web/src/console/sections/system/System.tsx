// The console's System section: alerts, maintenance, the guardrails (the studio's stop and limits), the render server, the agent's model, the app, the disk, backups,
// who uses the space, and how many of everything there is.

import { useState } from 'react';
import { api } from '../../../common/api';
import { Meter } from '../../../common/components/Charts';
import { useConsole, useSection } from '../shared/context';
import { Facts, Loaded, bytes, failed, number, span, stamp } from '../shared/ui';
import { BackupsCard, type Backups } from './Backups';
import { GuardrailsCard, type Guardrails } from './Guardrails';
import {
  AlertsCard,
  MaintenanceCard,
  ModelServerCard,
  type Alerts,
  type Maintenance,
  type ModelServer,
} from './Health';
import { StorageCards, type Storage } from './Storage';
import { ClientErrorsCard, type ClientErrors } from './ClientErrors';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../shared/Console.module.css';
import css3 from '../../../studio/pages/create/CreatePage.module.css';
const css = classesOf(css0, css1, css2, css3);

type Device = { name: string; type: string; vram_total: number; vram_free: number };
type State = {
  maintenance: Maintenance;
  model_server: ModelServer;
  server: {
    online: boolean;
    since: number;
    url: string;
    queue?: { running: number; pending: number };
    devices?: Device[];
    system?: {
      comfyui_version?: string;
      os?: string;
      python_version?: string;
      pytorch_version?: string;
      ram_total?: number;
      ram_free?: number;
    };
  };
  app: {
    version: string;
    uptime_seconds: number;
    python: string;
    os: string;
    ffmpeg: boolean;
    online_users: number;
    open_connections: number;
  };
  storage: {
    disk_total: number;
    disk_free: number;
    library: number;
    assets: number;
    database: number;
    database_kind: string;
    folder: string;
  };
  counts: Record<string, number>;
  tables?: { name: string; rows: number; bytes: number }[];
  restore_test?: { when: number; copy: string; ok: boolean; detail: string } | null;
  retention_days?: number;
};

const gb = (v: number) => (v / 1024 ** 3).toFixed(1) + ' GB';

function CheckNow() {
  const { refresh } = useConsole();
  const [busy, setBusy] = useState(false);
  return (
    <button
      className="btn small"
      disabled={busy}
      onClick={() => {
        setBusy(true);
        void api('/api/admin/server/check', { method: 'POST' })
          .then(refresh, failed)
          .finally(() => setBusy(false));
      }}
    >
      {busy ? 'Checking…' : 'Check now'}
    </button>
  );
}

export default function System() {
  const query = useSection('system', [], async () => {
    const [s, b, st, alerts, browsers, guard] = await Promise.all([
      api<State>('/api/admin/system'),
      api<Backups>('/api/admin/backups'),
      api<Storage>('/api/admin/storage'),
      api<Alerts>('/api/admin/alerts'),
      api<ClientErrors>('/api/admin/client-errors'),
      // shown to those whose role may read it
      api<Guardrails>('/api/admin/guardrails').catch(() => null),
    ]);
    return { s, b, st, alerts, browsers, guard };
  });
  return (
    <Loaded query={query}>
      {({ s, b, st, alerts, browsers, guard }) => {
        const sys = s.server.system || {};
        const disk = s.storage;
        return (
          <div className={css('grid-2')}>
            <AlertsCard a={alerts} />
            <MaintenanceCard key={String(s.maintenance.on)} m={s.maintenance} />
            {guard && <GuardrailsCard key={JSON.stringify(guard)} g={guard} />}
            <div className={css('card')}>
              <div className={css('card-head')}>
                <h2>Render server</h2>
                <span className={css('pill ' + (s.server.online ? 'done' : 'failed'))}>
                  {s.server.online ? 'Online' : 'Offline'}
                </span>
                <CheckNow />
              </div>
              <Facts
                pairs={[
                  [s.server.online ? 'Online since' : 'Offline since', stamp(s.server.since)],
                  ['Address', s.server.url],
                  ['ComfyUI', sys.comfyui_version],
                  ['Operating system', sys.os],
                  ['Python', sys.python_version && sys.python_version.split(' ')[0]],
                  ['PyTorch', sys.pytorch_version],
                  [
                    'ComfyUI queue',
                    s.server.queue &&
                      `${s.server.queue.running} running · ${s.server.queue.pending} waiting (all clients)`,
                  ],
                ]}
              />
              {!s.server.online && (
                <p className="muted">
                  It does not answer. Check that the render PC is on, Tailscale is connected and ComfyUI is started, and
                  that the address in Settings is right.
                </p>
              )}
              {(s.server.devices || []).map((d) => (
                <div key={d.name}>
                  <h3>{d.name.replace(/^cuda:\d+\s*/, '').split(' : ')[0] || d.type}</h3>
                  <Meter label="Video memory" used={d.vram_total - d.vram_free} total={d.vram_total} format={gb} />
                </div>
              ))}
              {sys.ram_total ? (
                <Meter
                  label="System memory"
                  used={sys.ram_total - (sys.ram_free ?? 0)}
                  total={sys.ram_total}
                  format={gb}
                />
              ) : null}
            </div>
            <ModelServerCard m={s.model_server} />
            <div className={css('card')}>
              <div className={css('card-head')}>
                <h2>Scene.ai app</h2>
              </div>
              <Facts
                pairs={[
                  ['Version', s.app.version],
                  ['Running for', span(s.app.uptime_seconds)],
                  ['Python', s.app.python],
                  ['Operating system', s.app.os],
                  ['ffmpeg (for long videos)', s.app.ffmpeg ? 'Available' : 'Missing: run the start script again'],
                  ['Users online now', String(s.app.online_users)],
                  ['Open browser tabs', String(s.app.open_connections)],
                ]}
              />
            </div>
            <div className={css('card')}>
              <div className={css('card-head')}>
                <h2>Disk</h2>
              </div>
              <Meter label="Disk" used={disk.disk_total - disk.disk_free} total={disk.disk_total} format={gb} />
              <Facts
                pairs={[
                  ['Library files', bytes(disk.library)],
                  ['Asset files', bytes(disk.assets)],
                  [
                    'Database',
                    `${bytes(disk.database)} · ${disk.database_kind === 'postgres' ? 'PostgreSQL' : disk.database_kind}`,
                  ],
                  ['Free space', gb(disk.disk_free)],
                  ['Folder', disk.folder],
                ]}
              />
            </div>
            <ClientErrorsCard c={browsers} />
            <BackupsCard b={b} />
            <StorageCards st={st} />
            <div className={css('card')}>
              <div className={css('card-head')}>
                <h2>Records</h2>
              </div>
              <Facts
                pairs={Object.entries(s.counts).map(
                  ([k, v]) => [k.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase()), number(v)] as const,
                )}
              />
            </div>
            {s.tables && (
              <div className={css('card')}>
                <div className={css('card-head')}>
                  <h2>Tables</h2>
                </div>
                <Facts
                  pairs={[
                    [
                      'Restore test',
                      s.restore_test
                        ? `${s.restore_test.ok ? 'Passed' : 'Failed'} · ${s.restore_test.copy} · ${s.restore_test.detail}`
                        : 'Not run (restore_test_url is not set)',
                    ],
                    [
                      "Agent's records kept",
                      s.retention_days
                        ? `${s.retention_days} days; older ones archived monthly`
                        : 'For good (retention_days 0)',
                    ],
                    ...s.tables.map((t) => [t.name, `${number(t.rows)} rows · ${bytes(t.bytes)}`] as const),
                  ]}
                />
              </div>
            )}
          </div>
        );
      }}
    </Loaded>
  );
}
