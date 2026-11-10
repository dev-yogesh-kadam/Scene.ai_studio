// The console's Audit log: who did what. Each entry is sealed with a hash of itself and the one before.

import { useState } from 'react';
import { api } from '../../../common/api';
import { useFilters, useSection } from '../shared/context';
import { ExportLink, Loaded, Person, SearchBox, Table, number, stamp } from '../shared/ui';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from './Audit.module.css';
import css3 from '../shared/Console.module.css';
const css = classesOf(css0, css1, css2, css3);

type Entry = {
  created: number;
  actor_name?: string;
  actor_email?: string;
  action: string;
  target: string;
  detail: string;
  ip: string;
};
type Verified = {
  ok: boolean;
  sealed?: number;
  since?: number;
  missing?: number;
  broken?: { action: string; created?: number; id?: number };
};

function words(v: Verified) {
  if (v.ok)
    return v.sealed
      ? `All ${number(v.sealed)} sealed entries hold${v.since ? ` (sealed since ${stamp(v.since)})` : ''}.`
      : 'No sealed entries yet.';
  if (v.missing) return `${number(v.missing)} entr${v.missing === 1 ? 'y was' : 'ies were'} taken out.`;
  return `Changed: ${v.broken?.action}${v.broken?.created ? ` at ${stamp(v.broken.created)}` : ''} (entry ${v.broken?.id ?? 'at the end'}).`;
}

/** Checks the seals of the audit log (backend/scene/audit.py): whether any entry was changed or taken out. */
function SealCheck() {
  const [said, setSaid] = useState({ text: '', good: true });
  const [busy, setBusy] = useState(false);
  const check = async () => {
    setBusy(true);
    try {
      const v = await api<Verified>('/api/admin/audit/verify');
      setSaid({ text: words(v), good: v.ok });
    } catch (e) {
      setSaid({ text: (e as Error).message, good: false });
    }
    setBusy(false);
  };
  return (
    <span className="row">
      <span className={css('small' + (said.text ? (said.good ? ' ok-text' : ' error') : ''))}>{said.text}</span>
      <button className="btn small" disabled={busy} onClick={() => void check()}>
        Check the seals
      </button>
    </span>
  );
}

export default function Audit() {
  const [s, set] = useFilters<{ q: string }>('audit');
  const query = useSection('audit', [s.q], () =>
    api<{ entries: Entry[] }>('/api/admin/audit?' + new URLSearchParams({ q: s.q })).then((a) => a.entries),
  );
  return (
    <Loaded query={query}>
      {(entries) => (
        <>
          <div className={css('toolbar')}>
            <SearchBox placeholder="Search person, action or target" value={s.q} onChange={(q) => set({ q })} />
            <span style={{ marginLeft: 'auto' }} />
            <SealCheck />
            <ExportLink name="audit" />
          </div>
          <div className={css('card')}>
            <Table
              head={['When', 'Who', 'Action', 'On', 'Details', 'Address']}
              rows={entries.map((e) => [
                stamp(e.created),
                e.actor_name ? (
                  <Person key="p" name={e.actor_name} email={e.actor_email} />
                ) : (
                  <span key="n" className="muted">
                    Not signed in
                  </span>
                ),
                e.action,
                e.target,
                e.detail,
                <span key="i" className="muted small">
                  {e.ip}
                </span>,
              ])}
              empty="No entries match."
            />
          </div>
          <p className="muted small" style={{ marginTop: 10 }}>
            Sign-ins, failed sign-ins, new accounts and every admin action are recorded here. The latest 300 are shown;
            Export CSV gives all of them. Each entry is sealed with a hash of itself and the entry before it, so an
            entry changed or taken out shows when the seals are checked.
          </p>
        </>
      )}
    </Loaded>
  );
}
