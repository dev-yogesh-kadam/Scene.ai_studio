// The console's Sessions section (admins only): every agent tab's Claude session, what it is doing now, and what
// happened in it, watched as it happens. /sessions lists them; /sessions/SES... watches one, /sessions/SESa,SESb several
// side by side. Watch only: nothing here writes to a session. See backend/scene/sessions.py.

import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { api } from '../../../common/api';
import { useConsole, useFilters, useSection } from '../shared/context';
import { Loaded, Person, SearchBox, Table, ago, number } from '../shared/ui';
import { Fullness, StatePill, where, type SessionRow } from './parts';
import { Pane } from './Pane';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from './Sessions.module.css';
import css3 from '../shared/Console.module.css';
import css4 from '../../../studio/pages/create/CreatePage.module.css';
const css = classesOf(css0, css1, css2, css3, css4);

const STATES = [
  { id: '', label: 'All' },
  { id: 'answering', label: 'Answering' },
  { id: 'live', label: 'Live' },
  { id: 'idle', label: 'Idle' },
  { id: 'deleted', label: 'Deleted' },
];

type Found = { sessions: (SessionRow & { title?: string })[]; counts: Record<string, number> };

function List() {
  const navigate = useNavigate();
  const { refresh } = useConsole();
  const [s, set] = useFilters<{ q: string; state: string }>('sessions');
  const [picked, setPicked] = useState<string[]>([]);
  const query = useSection('sessions', [s.q, s.state], () =>
    api<Found>(`/api/admin/sessions?q=${encodeURIComponent(s.q)}&state=${s.state}`),
  );
  // The list follows what the sessions do while it is open.
  useEffect(() => {
    const timer = setInterval(() => {
      if (!picked.length && !document.hidden) void refresh();
    }, 5000);
    return () => clearInterval(timer);
  }, [picked.length, refresh]);
  return (
    <Loaded query={query}>
      {(found) => (
        <div className={css('card')}>
          <div className={css('card-head')}>
            <h2>Claude sessions</h2>
            <SearchBox
              placeholder="Session, tab, project id, person or email"
              value={s.q}
              onChange={(q) => set({ q })}
            />
          </div>
          <div className="row" style={{ marginBottom: 10 }}>
            <div className={css('chips')}>
              {STATES.map((st) => (
                <button
                  key={st.id}
                  className={'btn small' + (s.state === st.id ? ' primary' : '')}
                  onClick={() => set({ state: st.id })}
                >
                  {st.label + (st.id && found.counts[st.id] ? ` · ${found.counts[st.id]}` : '')}
                </button>
              ))}
            </div>
            <span style={{ flex: 1 }} />
            <button
              className="btn small primary"
              disabled={!picked.length}
              onClick={() => void navigate('/sessions/' + picked.join(','))}
            >
              {picked.length > 1 ? `Watch ${picked.length} side by side` : 'Watch side by side'}
            </button>
          </div>
          <Table
            head={['', 'Session', 'Person', 'Project', 'Model', 'Context', 'Messages', 'Now', 'Last active']}
            rows={found.sessions.map((r) => [
              <input
                key="t"
                type="checkbox"
                aria-label={'Pick ' + r.ref}
                checked={picked.includes(r.ref)}
                onClick={(e) => e.stopPropagation()}
                onChange={(e) =>
                  setPicked((was) => (e.target.checked ? [...was, r.ref] : was.filter((x) => x !== r.ref)))
                }
              />,
              <Person key="s" name={r.title || 'Studio session'} email={r.ref} />,
              <Person key="p" name={r.user_name} email={r.user_email} />,
              <Person
                key="w"
                name={where(r)}
                email={[r.parent_ref, r.project_ref].filter(Boolean).join(' › ') || ''}
              />,
              r.model || '—',
              <Fullness key="f" s={r} />,
              number(r.messages),
              <StatePill key="n" state={r.state} />,
              ago(r.active),
            ])}
            onRow={(i) => void navigate('/sessions/' + found.sessions[i].ref)}
            empty={s.q || s.state ? 'No session matches.' : 'No agent tab has used Claude yet.'}
          />
          <p className="muted small" style={{ marginTop: 10 }}>
            One session for each agent tab of a project. It goes on across days and model changes, and is compacted,
            still the same session, when its context is 90% full. Nothing is ever deleted here. Watch only.
          </p>
        </div>
      )}
    </Loaded>
  );
}

function Watch({ refs }: { refs: string[] }) {
  return (
    <>
      <div className="row" style={{ marginBottom: 12 }}>
        <Link className="btn small" to="/sessions">
          ← All sessions
        </Link>
        <span className="muted small">
          {refs.length > 1 ? `${refs.length} sessions side by side, as they happen` : 'As it happens'}
        </span>
      </div>
      <div className={css('ses-grid' + (refs.length > 1 ? ' many' : ''))}>
        {refs.map((ref) => (
          <Pane key={ref} sessionRef={ref} alone={refs.length === 1} />
        ))}
      </div>
    </>
  );
}

export default function Sessions() {
  const location = useLocation();
  const refs = (location.pathname.split('/')[2] || '').split(',').filter((r) => /^SES[A-Za-z0-9]{13}$/.test(r));
  return refs.length ? <Watch refs={refs} /> : <List />;
}
