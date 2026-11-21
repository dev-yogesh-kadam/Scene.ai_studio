// The Overview's cards that act: who is online, new accounts, the queue and its controls, recent activity, earnings.

import { api } from '../../../common/api';
import { useConsole } from '../shared/context';
import { ago, failed, number, sure } from '../shared/ui';
import type { Overview, Queue } from './types';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared.module.css';
import css1 from '../../../common/components/Shared2.module.css';
import css2 from '../../../common/components/Shared3.module.css';
import css3 from '../jobs/JobDrawer.module.css';
import css4 from './Cards.module.css';
import css5 from './Overview.module.css';
import css6 from './Shared.module.css';
import css7 from '../shared/Console.module.css';
import css8 from '../../../studio/pages/create/CreatePage.module.css';
import css9 from '../../../studio/pages/projects/ProjectsPage.module.css';
import css10 from '../../../studio/pages/projects/projects.module.css';
const css = classesOf(css0, css1, css2, css3, css4, css5, css6, css7, css8, css9, css10);

const DOT: Record<string, string> = { done: 'good', failed: 'critical', cancelled: 'warning', audit: 'neutral' };
// The studio's pages, as a tab reports them, in the words of the menu.
const PAGE: Record<string, string> = {
  '/home': 'Home',
  '/projects': 'All projects',
  '/library': 'Library',
  '/create': 'Create',
  '/canvas': 'Canvas',
  '/settings': 'Settings',
  '/admin': 'Admin console',
};
const rupees = (value: number | null | undefined) => '₹' + Math.round(value || 0).toLocaleString();
const clock = (timestamp: number) =>
  new Date(timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

function useAct() {
  const { refresh } = useConsole();
  return (request: Promise<unknown>) => void request.then(refresh, failed);
}

/** Who has the studio open now, where, and what they are making. */
export function Online({ people }: { people: Overview['online'] }) {
  return (
    <div className={css('card')}>
      <div className={css('card-head')}>
        <h2>Online now</h2>
        <span className="muted small">{people.length === 1 ? '1 person' : `${people.length} people`}</span>
      </div>
      {people.length ? (
        people.map((p, i) => (
          <div key={i} className={css('feed-row')}>
            <div className={css('avatar small')}>{(p.name[0] || '?').toUpperCase()}</div>
            <div className={css('feed-text')}>
              <b>{p.name}</b>
              {p.role === 'admin' ? <span className="muted small"> · admin</span> : null}
              <div className="muted small">
                {[
                  p.pages.map((page) => PAGE[page] || page).join(', ') || 'Opening the studio',
                  p.tabs > 1 && `${p.tabs} tabs`,
                  p.job && `${p.job.status === 'running' ? 'making' : 'waiting for'} "${p.job.name}"`,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </div>
            </div>
            <span className="muted small">{'since ' + clock(p.since)}</span>
          </div>
        ))
      ) : (
        <div className={css('empty')}>Nobody has the studio open.</div>
      )}
    </div>
  );
}

/** New accounts: whether anyone may sign up, how many came today, and a quick way to stop one. */
export function Signups({ s }: { s: Overview['signups'] }) {
  const act = useAct();
  return (
    <div className={css('card')}>
      <div className={css('card-head')}>
        <h2>New accounts</h2>
        <span className="muted small">
          {`${s.today} in the last 24 hours` + (s.per_day ? ` · ${s.per_day} a day allowed from one address` : '')}
        </span>
        <button
          className={'btn small' + (s.open ? '' : ' primary')}
          onClick={() => {
            void (
              s.open
                ? sure(
                    'Close sign-up? Nobody new can create an account until you open it again. Existing accounts are not affected.',
                  )
                : Promise.resolve(true)
            ).then((yes) => {
              if (yes) act(api('/api/admin/settings', { method: 'PUT', json: { allow_signup: !s.open } }));
            });
          }}
        >
          {s.open ? 'Close sign-up' : 'Open sign-up'}
        </button>
      </div>
      <p className="muted small" style={{ margin: '-6px 0 8px' }}>
        {s.open ? 'Sign-up is open: anyone who finds the site can make an account.' : 'Sign-up is closed.'}
      </p>
      {s.recent.length ? (
        s.recent.map((u) => (
          <div key={u.id} className={css('feed-row')}>
            <div className={css('feed-text')}>
              <b>{u.name}</b>
              {u.disabled ? (
                <span className={css('pill failed')} style={{ marginLeft: 6 }}>
                  Disabled
                </span>
              ) : null}
              <div className="muted small">
                {[u.email, u.ip, `${u.jobs} job${u.jobs === 1 ? '' : 's'}`].filter(Boolean).join(' · ')}
              </div>
            </div>
            <span className="muted small">{ago(u.created)}</span>
            <button
              className={'btn small quiet' + (u.disabled ? '' : ' danger')}
              onClick={() => {
                void (
                  u.disabled
                    ? Promise.resolve(true)
                    : sure(`Disable ${u.name}? They are signed out and can't sign in until you enable them again.`)
                ).then((yes) => {
                  if (yes) act(api('/api/admin/users/' + u.id, { method: 'PUT', json: { disabled: !u.disabled } }));
                });
              }}
            >
              {u.disabled ? 'Enable' : 'Disable'}
            </button>
          </div>
        ))
      ) : (
        <div className={css('empty')}>No accounts yet.</div>
      )}
    </div>
  );
}

export function QueueCard({ q }: { q: Queue }) {
  const { go } = useConsole();
  const act = useAct();
  const running = q.running;
  const share =
    running && running.steps
      ? Math.round((100 * (Math.max(running.clip, 1) - 1 + running.step / running.steps)) / Math.max(running.clips, 1))
      : 0;
  return (
    <div className={css('card')}>
      <div className={css('card-head')}>
        <h2>Queue right now</h2>
        <button
          className={'btn small' + (q.paused ? ' primary' : '')}
          title={
            q.paused
              ? 'Let waiting jobs start again'
              : 'Waiting renders stay waiting; the one running finishes. Edits and motion graphics keep running.'
          }
          onClick={() => act(api('/api/admin/queue', { method: 'PUT', json: { paused: !q.paused } }))}
        >
          {q.paused ? 'Resume renders' : 'Pause renders'}
        </button>
        <button className="btn small quiet" onClick={() => go('jobs')}>
          All jobs
        </button>
      </div>
      {q.paused && (
        <div className={css('alert warning static')}>
          <span className={css('alert-level')}>Paused</span>
          <span className={css('alert-text')}>
            Renders are paused. Jobs wait until you resume them; users see them as waiting.
          </span>
        </div>
      )}
      {running ? (
        <div className={css('job')}>
          <div className={css('job-head')}>
            <span className={css('name')}>{running.name}</span>
            <span className={css('pill running')}>Running</span>
          </div>
          <div
            className={css('sub')}
          >{`${running.user_name} · ${running.workflow} · started ${ago(running.started)}`}</div>
          <div className={css('bar' + (running.steps ? '' : ' busy'))}>
            <div style={running.steps ? { width: `${share}%` } : undefined} />
          </div>
          <div className={css('sub')}>
            {[
              running.clips > 1 && `Clip ${running.clip} of ${running.clips}`,
              running.steps ? `Step ${running.step} of ${running.steps}` : 'Starting',
              running.node,
            ]
              .filter(Boolean)
              .join(' · ')}
          </div>
        </div>
      ) : (
        <div className={css('empty')}>Nothing is rendering.</div>
      )}
      {q.waiting.length > 0 && (
        <div>
          <h3>{`Waiting (${q.waiting_total})`}</h3>
          {q.waiting.map((j, i) => (
            <div key={j.id} className={css('feed-row')}>
              <span className="muted">{`${i + 1}.`}</span>
              <span className={css('feed-text')}>
                {j.name}
                <span className="muted">{` · ${j.user_name}`}</span>
                <div className="muted small">
                  {'added ' + ago(j.created) + (j.priority ? ' · moved to the front' : '')}
                </div>
              </span>
              {i > 0 && (
                <button
                  className="btn small quiet"
                  title="Start this one next"
                  onClick={() => act(api(`/api/admin/jobs/${j.id}/front`, { method: 'POST' }))}
                >
                  To front
                </button>
              )}
              <button
                className="btn small quiet danger"
                onClick={() => {
                  void sure(`Cancel "${j.name}"? ${j.user_name} gets the credits back.`).then((yes) => {
                    if (yes) act(api('/api/admin/jobs/' + j.id, { method: 'DELETE' }));
                  });
                }}
              >
                Cancel
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function Activity({ rows }: { rows: Overview['activity'] }) {
  const { go } = useConsole();
  return (
    <div className={css('card')}>
      <div className={css('card-head')}>
        <h2>Recent activity</h2>
        <button className="btn small quiet" onClick={() => go('audit')}>
          Audit log
        </button>
      </div>
      {rows.length ? (
        rows.map((a, i) => (
          <div key={i} className={css('feed-row')}>
            <span className={css('status-dot ' + DOT[a.kind])} />
            <span className={css('feed-text')}>
              <b>{a.who || 'Someone'}</b> {a.text}
            </span>
            <span className="muted small">{ago(a.time)}</span>
          </div>
        ))
      ) : (
        <div className={css('empty')}>No activity yet.</div>
      )}
    </div>
  );
}

/** What each workflow earned against what its electricity cost, in this period. */
export function Earnings({ money, days }: { money: Overview['economics']; days: number }) {
  const { go } = useConsole();
  const top = Math.max(1, ...money.workflows.map((w) => Math.max(w.revenue_inr || 0, w.electricity_inr || 0)));
  return (
    <div className={css('card')}>
      <div className={css('card-head')}>
        <h2>Earnings and electricity</h2>
        <span className="muted small">
          {money.totals.revenue_inr
            ? `${rupees(money.totals.revenue_inr)} earned · ${rupees(money.totals.electricity_inr)} electricity · ${money.totals.margin_percent}% left`
            : `last ${days} days`}
        </span>
        <button className="btn small quiet" onClick={() => go('economics')}>
          Economics
        </button>
      </div>
      {money.workflows.length ? (
        <>
          <div className={css('earn-list')}>
            {money.workflows.map((w) => (
              <div
                key={w.title}
                className={css('earn-row' + (w.margin_inr != null && w.margin_inr < 0 ? ' losing' : ''))}
              >
                <div className={css('earn-name')}>
                  <b>{w.title}</b>
                  <span className="muted small">{`${number(w.done)} made`}</span>
                </div>
                <div
                  className={css('earn-bars')}
                  title={`${rupees(w.revenue_inr)} earned, ${w.electricity_inr == null ? 'electricity not known' : rupees(w.electricity_inr) + ' electricity'}`}
                >
                  <i className={css('earned')} style={{ width: `${(100 * (w.revenue_inr || 0)) / top}%` }} />
                  <i className={css('spent')} style={{ width: `${(100 * (w.electricity_inr || 0)) / top}%` }} />
                </div>
                <div className={css('earn-figure')}>
                  {w.margin_inr == null ? <span className="muted">power not known</span> : rupees(w.margin_inr)}
                </div>
              </div>
            ))}
          </div>
          <div className={css('legend')}>
            <span>
              <i className={css('swatch earned')} />
              Earned
            </span>
            <span>
              <i className={css('swatch spent')} />
              Electricity
            </span>
            <span>Right: what is left</span>
          </div>
        </>
      ) : (
        <div className={css('empty')}>{`No finished jobs in the last ${days} days.`}</div>
      )}
      {money.unmeasured.length > 0 && (
        <p className="muted small">{`The power of ${money.unmeasured.join(', ')} is not set (Pricing, Servers), so its electricity is not counted.`}</p>
      )}
    </div>
  );
}
