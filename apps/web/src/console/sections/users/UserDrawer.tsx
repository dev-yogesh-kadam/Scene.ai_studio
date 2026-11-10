// One person in the console: what they have done, their credits and items, and how to manage the account.

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../../../common/api';
import { askText } from '../../../common/components/Dialog';
import { CreditsDialog } from '../credits/CreditsDialog';
import { REASON } from '../credits/reasons';
import { useConsole } from '../shared/context';
import { Drawer } from '../shared/Drawer';
import { Facts, Pill, Section, Table, Thumb, Tile, ago, bytes, failed, number, span, stamp, sure } from '../shared/ui';
import type { UserRow } from './Users';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared.module.css';
import css1 from '../../../common/components/Shared2.module.css';
import css2 from '../../../common/components/Shared3.module.css';
import css3 from '../shared/Console.module.css';
import css4 from './UserDrawer.module.css';
import css5 from '../../../studio/pages/projects/projects.module.css';
const css = classesOf(css0, css1, css2, css3, css4, css5);

export type StaffRole = { id: string; label: string; about?: string };

type Limits = { exempt?: boolean; own: number | null; studio: number; spent_today: number; in_force: number };
type SessionRow = {
  key: string;
  console?: boolean;
  agent?: string;
  ip?: string;
  seen?: number;
  created: number;
  here?: boolean;
};
type Detail = {
  user: UserRow & { mfa_enabled: number | boolean; last_sign_in: number | null };
  stats: { done: number; failed: number; cancelled: number; gpu_seconds: number };
  storage_bytes: number;
  assets: number;
  projects: number;
  limits: Limits;
  sessions: SessionRow[];
  items: { id: number; kind: string; name: string }[];
  jobs: { id: string; name: string; status: string; cost: number; created: number; error?: string; summary?: string }[];
  credits: { created: number; amount: number; reason: string; job_name?: string; note?: string }[];
};

/** "Chrome on Windows", from a browser's own description of itself. */
function browserName(agent?: string) {
  if (!agent) return 'Unknown browser';
  const browser = /Edg\//.test(agent)
    ? 'Edge'
    : /OPR\//.test(agent)
      ? 'Opera'
      : /Firefox\//.test(agent)
        ? 'Firefox'
        : /Chrome\//.test(agent)
          ? 'Chrome'
          : /Safari\//.test(agent)
            ? 'Safari'
            : /python|curl|node|httpx/i.test(agent)
              ? 'A script'
              : 'A browser';
  const system = /Windows/.test(agent)
    ? 'Windows'
    : /Android/.test(agent)
      ? 'Android'
      : /iPhone|iPad/.test(agent)
        ? 'iPhone or iPad'
        : /Mac OS X/.test(agent)
          ? 'Mac'
          : /Linux/.test(agent)
            ? 'Linux'
            : '';
  return system ? `${browser} on ${system}` : browser;
}

function Actions({ u, roles, after }: { u: Detail['user']; roles: StaffRole[]; after: () => void }) {
  const { user } = useConsole();
  const [giving, setGiving] = useState(false);
  const put = (json: unknown) => api('/api/admin/users/' + u.id, { method: 'PUT', json }).then(after, failed);
  const self = u.id === user.id;
  const admin = user.role === 'admin';
  const choices: StaffRole[] = [{ id: 'user', label: 'User', about: 'no console' }, ...roles];
  return (
    <div className="row">
      <button className="btn small primary" onClick={() => setGiving(true)}>
        Give or take credits
      </button>
      <button
        className="btn small"
        onClick={() => {
          void askText({
            maxLength: 200,
            title: `New password for ${u.name} (at least 8 characters). They are signed out everywhere.`,
          }).then((password) => {
            if (password) void put({ password });
          });
        }}
      >
        Set password
      </button>
      {!self && admin && (
        <label className="role-pick">
          {'Role '}
          <select
            value={u.role}
            onChange={(e) => {
              const role = e.target.value;
              const chosen = choices.find((r) => r.id === role);
              void sure(`Make ${u.name} ${chosen?.label}${chosen?.about ? ` (${chosen.about})` : ''}?`).then((yes) => {
                if (yes) void put({ role });
              });
            }}
          >
            {choices.map((r) => (
              <option key={r.id} value={r.id} title={r.about}>
                {r.label}
              </option>
            ))}
          </select>
        </label>
      )}
      {!self && admin && u.role !== 'admin' && !u.disabled && (
        <button
          className="btn small"
          title="Opens the studio as they see it, read only, for an hour"
          onClick={() => {
            void sure(
              `View the studio as ${u.name}, read only? It opens in a new tab and is written in the audit log. In this browser your own studio sign-in is replaced while you view.`,
            ).then(async (yes) => {
              if (!yes) return;
              try {
                const view = await api<{ port: number; path: string }>(`/api/admin/users/${u.id}/view`, {
                  method: 'POST',
                });
                window.open(
                  `${location.protocol}//${location.hostname}:${view.port}${view.path}`,
                  '_blank',
                  'noopener',
                );
              } catch (e) {
                failed(e);
              }
            });
          }}
        >
          View the studio as them
        </button>
      )}
      {u.mfa_enabled ? (
        <button
          className="btn small"
          onClick={() => {
            void sure(
              `Turn off two-step sign-in for ${u.name}? Do this only when you know it is them asking, for example after a lost phone. They are signed out everywhere.`,
            ).then((yes) => {
              if (yes) void put({ mfa_off: true });
            });
          }}
        >
          Turn off two-step sign-in
        </button>
      ) : null}
      {!self && (
        <button
          className="btn small quiet danger"
          onClick={() => {
            void (
              u.disabled
                ? Promise.resolve(true)
                : sure(`Disable ${u.name}? They are signed out and can't sign in until you enable them again.`)
            ).then((yes) => {
              if (yes) void put({ disabled: !u.disabled });
            });
          }}
        >
          {u.disabled ? 'Enable account' : 'Disable account'}
        </button>
      )}
      {giving && (
        <CreditsDialog
          people={[u]}
          onClose={() => setGiving(false)}
          after={() => {
            setGiving(false);
            after();
          }}
        />
      )}
    </div>
  );
}

/** How many credits the user may spend in 24 hours: the studio's limit, their own, or none. */
function Limit({ d, after }: { d: Detail; after: () => void }) {
  const l = d.limits;
  const [box, setBox] = useState(l.own == null ? '' : String(l.own));
  if (l.exempt)
    return (
      <Section title="Daily spending limit">
        <p className="muted">Admins have no daily limit.</p>
      </Section>
    );
  const save = (value: number | null) =>
    api('/api/admin/users/' + d.user.id, { method: 'PUT', json: { daily_cap: value } }).then(after, failed);
  return (
    <Section title="Daily spending limit">
      <p className="muted small">
        {`${number(l.spent_today)} credits spent in the last 24 hours. `}
        {l.in_force
          ? `The limit in force is ${number(l.in_force)}${l.own == null ? " (the studio's)" : ' (their own)'}.`
          : 'No limit is in force for them.'}
      </p>
      <div className="row" style={{ marginTop: 8 }}>
        <input
          type="number"
          min={0}
          step={50}
          value={box}
          placeholder={l.studio ? `Studio limit: ${number(l.studio)}` : 'Studio: no limit'}
          style={{ width: 180 }}
          onChange={(e) => setBox(e.target.value)}
        />
        <button className="btn small" onClick={() => void save(box === '' ? null : Number(box))}>
          Save
        </button>
        {l.own != null && (
          <button className="btn small quiet" onClick={() => void save(null)}>
            Use the studio&apos;s limit
          </button>
        )}
      </div>
      <p className="muted small" style={{ marginTop: 6 }}>
        Leave it empty to follow the studio&apos;s limit (Settings). 0 means no limit for this user.
      </p>
    </Section>
  );
}

function SignedIn({ d, after }: { d: Detail; after: () => void }) {
  const end = async (key: string) => {
    if (
      !(await sure(
        key ? 'Sign out this session?' : `Sign ${d.user.name} out everywhere, in the studio and this console?`,
      ))
    )
      return;
    try {
      await api(`/api/admin/users/${d.user.id}/sign-out`, { method: 'POST', json: key ? { key } : {} });
      after();
    } catch (e) {
      failed(e);
    }
  };
  const others = d.sessions.filter((x) => !x.here);
  return (
    <Section title={`Signed in (${d.sessions.length})`}>
      {d.sessions.length ? (
        <Table
          head={['Where', 'Browser', 'Address', 'Last used', '']}
          rows={d.sessions.map((x) => [
            x.console ? 'Admin console' : 'Studio',
            browserName(x.agent),
            x.ip || '',
            ago(x.seen || x.created),
            x.here ? (
              <span key="h" className="muted small">
                You, here
              </span>
            ) : (
              <button key="b" className="btn small quiet" onClick={() => void end(x.key)}>
                Sign out
              </button>
            ),
          ])}
        />
      ) : (
        <p className="muted">Not signed in anywhere.</p>
      )}
      {others.length > 1 && (
        <button className="btn small quiet danger" style={{ marginTop: 8 }} onClick={() => void end('')}>
          Sign out everywhere
        </button>
      )}
    </Section>
  );
}

function Body({ d, roles, after }: { d: Detail; roles: StaffRole[]; after: () => void }) {
  const u = d.user;
  return (
    <>
      <div className={css('drawer-title')}>
        <div className={css('avatar')}>{(u.name[0] || '?').toUpperCase()}</div>
        <div>
          <b>{u.name}</b>
          <div className="muted">{u.email}</div>
        </div>
        <span className={css('pill ' + (u.role !== 'user' ? 'running' : 'queued'))}>{u.role}</span>
        {u.mfa_enabled ? <span className={css('pill done')}>Two-step</span> : null}
        {u.disabled ? <span className={css('pill failed')}>Disabled</span> : null}
      </div>
      <div className={css('tiles small-tiles')}>
        <Tile label="Credits" value={number(u.credits)} sub={`${number(u.spent)} spent`} />
        <Tile
          label="Jobs"
          value={number(u.jobs)}
          sub={`${d.stats.done} done · ${d.stats.failed} failed · ${d.stats.cancelled} cancelled`}
        />
        <Tile label="GPU time" value={span(d.stats.gpu_seconds) || '0 s'} />
        <Tile
          label="Library"
          value={number(u.generations)}
          sub={`${bytes(d.storage_bytes)} · ${d.assets} assets · ${d.projects} projects`}
        />
      </div>
      <Actions u={u} roles={roles} after={after} />
      <Limit key={String(d.limits.own)} d={d} after={after} />
      <Section title="Account">
        <Facts
          pairs={[
            ['Joined', stamp(u.created)],
            ['Last sign-in', u.last_sign_in ? stamp(u.last_sign_in) : 'No active session'],
            ['Last job', u.last_job ? stamp(u.last_job) : 'Never'],
          ]}
        />
      </Section>
      <SignedIn d={d} after={after} />
      <Section title="Latest items">
        {d.items.length ? (
          <div className={css('thumbs')}>
            {d.items.map((i) => (
              <div key={i.id} className={css('thumb-box')} title={i.name}>
                <Thumb item={i} />
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">Nothing made yet.</p>
        )}
      </Section>
      <Section title="Latest jobs">
        <Table
          head={['Job', 'Status', 'Credits', 'Added']}
          rows={d.jobs.map((j) => [
            <div key="j">
              {j.name}
              <div className={j.error ? 'error small' : 'muted small'}>{j.error || j.summary}</div>
            </div>,
            <Pill key="p" status={j.status} />,
            String(j.cost),
            ago(j.created),
          ])}
          empty="No jobs yet."
        />
      </Section>
      <Section title="Credit history">
        <Table
          head={['When', 'Credits', 'Reason']}
          rows={d.credits.map((c) => [
            ago(c.created),
            (c.amount > 0 ? '+' : '') + c.amount,
            REASON[c.reason] +
              [c.job_name, c.note]
                .filter(Boolean)
                .map((x) => ` · ${x}`)
                .join(''),
          ])}
          empty="No credit changes."
        />
      </Section>
    </>
  );
}

export function UserDrawer({ id, roles, onClose }: { id: number; roles: StaffRole[]; onClose: () => void }) {
  const client = useQueryClient();
  const { refresh } = useConsole();
  const query = useQuery({ queryKey: ['console', 'user', id], queryFn: () => api<Detail>('/api/admin/users/' + id) });
  const after = () => {
    void client.invalidateQueries({ queryKey: ['console', 'user', id] });
    void refresh();
  };
  return (
    <Drawer title="User" onClose={onClose}>
      {() =>
        query.error ? (
          <p className="error">{query.error.message}</p>
        ) : query.data ? (
          <Body d={query.data} roles={roles} after={after} />
        ) : (
          <p className="muted">Loading…</p>
        )
      }
    </Drawer>
  );
}
