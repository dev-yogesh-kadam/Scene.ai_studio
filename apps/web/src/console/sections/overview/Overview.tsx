// Admin overview: what needs attention, the headline numbers with trends, who is online, new accounts, the live queue
// and its controls, earnings against electricity, charts and rankings.

import { api } from '../../../common/api';
import { BarList, ChartCard, Sparkline } from '../../../common/components/Charts';
import { Segmented } from '../../../common/components/Segmented';
import { useConsole, useSection } from '../shared/context';
import { Loaded, Table, ago, number, secondsSince, span } from '../shared/ui';
import { Activity, Earnings, Online, QueueCard, Signups } from './Cards';
import type { Health, Overview as Data, Queue } from './types';
import type { ReactNode } from 'react';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../jobs/JobDrawer.module.css';
import css3 from './Cards.module.css';
import css4 from './Overview.module.css';
import css5 from './Shared.module.css';
import css6 from '../shared/Console.module.css';
import css7 from '../../../studio/pages/create/CreatePage.module.css';
import css8 from '../../../studio/pages/projects/ProjectsPage.module.css';
const css = classesOf(css0, css1, css2, css3, css4, css5, css6, css7, css8);

const LEVEL: Record<string, string> = { critical: 'Critical', serious: 'Problem', warning: 'Check' };

/** "12% more than the 30 days before". `goodUp` says which direction is good news. */
function Change({
  now,
  before,
  days,
  goodUp = true,
}: {
  now: number | null;
  before: number | null;
  days: number;
  goodUp?: boolean;
}) {
  if (now == null || before == null) return <div className={css('delta muted')}>No earlier data to compare</div>;
  if (!before)
    return <div className={css('delta muted')}>{now ? `Nothing in the ${days} days before` : 'No change'}</div>;
  const percent = Math.round((100 * (now - before)) / before);
  if (percent === 0) return <div className={css('delta muted')}>{`Same as the ${days} days before`}</div>;
  return (
    <div className={css('delta ' + (percent > 0 === goodUp ? 'good' : 'bad'))}>
      <span className={css('arrow')}>{percent > 0 ? '▲' : '▼'}</span>
      {` ${Math.abs(percent)}% `}
      <span className="muted">{`vs the ${days} days before`}</span>
    </div>
  );
}

function Kpi({
  label,
  value,
  delta,
  trend,
  note,
}: {
  label: string;
  value: ReactNode;
  delta: ReactNode;
  trend: number[];
  note?: string;
}) {
  return (
    <div className={css('tile kpi')}>
      <div className={css('tile-label')}>{label}</div>
      <div className={css('tile-value')}>{value}</div>
      {note && <div className={css('tile-note')}>{note}</div>}
      {delta}
      {trend && <Sparkline values={trend} />}
    </div>
  );
}

/** The studio at a glance, at the top: each part of it as a dot and a word, each leading to the section about it. */
function HealthStrip({ h, queue }: { h: Health; queue: Queue }) {
  const { go } = useConsole();
  const age = (t: number) => secondsSince(t) / 86400;
  const chip = (state: string, label: string, value: string, tab: string) => (
    <button key={label} className={css('health-chip ' + state)} onClick={() => go(tab)}>
      <span className={css('health-dot')} />
      <span className="muted small">{label}</span>
      <b>{value}</b>
    </button>
  );
  const gbFree = h.disk_free / 1024 ** 3;
  return (
    <div className={css('health-strip')}>
      {chip(h.render ? 'good' : 'bad', 'Render server', h.render ? 'Online' : 'Offline', 'system')}
      {h.model !== null && chip(h.model ? 'good' : 'bad', 'Model server', h.model ? 'Online' : 'Offline', 'system')}
      {chip(
        queue.paused ? 'warn' : 'good',
        'Queue',
        queue.paused ? 'Paused' : `${queue.running ? 1 : 0} running · ${queue.waiting_total} waiting`,
        'jobs',
      )}
      {chip(h.alerts ? 'bad' : 'good', 'Alerts', h.alerts ? `${h.alerts} open` : 'None', 'system')}
      {h.maintenance && chip('warn', 'Maintenance', 'On', 'system')}
      {chip(gbFree < 10 ? 'bad' : gbFree < 50 ? 'warn' : 'good', 'Disk', `${gbFree.toFixed(0)} GB free`, 'system')}
      {chip(
        !h.backups_on ? 'warn' : !h.last_backup || age(h.last_backup) > 2 ? 'bad' : 'good',
        'Backup',
        !h.backups_on ? 'Off' : h.last_backup ? ago(h.last_backup) : 'None yet',
        'system',
      )}
      {chip(
        !h.node_list || age(h.node_list) > 3 ? 'warn' : 'good',
        'Node list',
        h.node_list ? ago(h.node_list) : 'None',
        'workflows',
      )}
    </div>
  );
}

function Rankings({ o }: { o: Data }) {
  const { go } = useConsole();
  return (
    <div className={css('grid-3')}>
      <div className={css('card')}>
        <div className={css('card-head')}>
          <h2>Most active users</h2>
          <span className="muted small">credits spent</span>
        </div>
        {o.top_users.length ? (
          <BarList
            rows={o.top_users.map((u) => ({
              label: u.name,
              sub: `${u.jobs} jobs`,
              value: u.credits || 0,
              title: `${u.email} · GPU ${span(u.gpu_seconds)}`,
            }))}
            format={number}
          />
        ) : (
          <div className={css('empty')}>No jobs in this period.</div>
        )}
      </div>
      <div className={css('card')}>
        <div className={css('card-head')}>
          <h2>Workflows used</h2>
        </div>
        <Table
          head={['Workflow', 'Jobs', 'Succeeded', 'Avg. time']}
          rows={o.top_workflows.map((w) => [
            w.workflow.split('/')[1].replace(/_/g, ' '),
            number(w.jobs),
            w.done + w.failed ? Math.round((100 * w.done) / (w.done + w.failed)) + '%' : '',
            span(w.avg_seconds),
          ])}
          empty="No jobs in this period."
        />
      </div>
      <div className={css('card')}>
        <div className={css('card-head')}>
          <h2>Why jobs failed</h2>
          <button className="btn small quiet" onClick={() => go('jobs', { status: 'failed' })}>
            Failed jobs
          </button>
        </div>
        {o.failures.length ? (
          o.failures.map((f, i) => (
            <div key={i} className={css('feed-row top')}>
              <b>{f.jobs + '×'}</b>
              <span className={css('feed-text small')}>{f.error || 'No error message'}</span>
              <span className="muted small">{ago(f.last_seen)}</span>
            </div>
          ))
        ) : (
          <div className={css('empty')}>No failed jobs in this period.</div>
        )}
      </div>
    </div>
  );
}

export default function Overview() {
  const { days: asked, setDays, go } = useConsole();
  const query = useSection('overview', [asked], () => api<Data>('/api/admin/overview?days=' + asked));
  return (
    <Loaded query={query}>
      {(o) => {
        const { current: now, previous: before, series, days, calendar: labels } = o;
        return (
          <>
            <div className={css('toolbar')}>
              <span className="muted">Period</span>
              <Segmented
                choices={[7, 30, 90].map((d) => ({ id: d, label: `${d} days` }))}
                current={days}
                onPick={setDays}
              />
              {o.announcement.text && (
                <button className="btn small quiet" title="Change it in Settings" onClick={() => go('settings')}>
                  Announcement showing
                </button>
              )}
              <span className="muted small" style={{ marginLeft: 'auto' }}>
                {'Updated ' + new Date(query.dataUpdatedAt).toLocaleTimeString()}
              </span>
            </div>
            <HealthStrip h={o.health} queue={o.queue} />
            {o.attention.length ? (
              <div className={css('attention')}>
                {o.attention.map((a, i) => (
                  <button key={i} className={css('alert ' + a.level)} onClick={() => go(a.tab)}>
                    <span className={css('alert-level')}>{LEVEL[a.level]}</span>
                    <span className={css('alert-text')}>{a.text}</span>
                    <span className="muted small">Open</span>
                  </button>
                ))}
              </div>
            ) : (
              <div className={css('all-clear')}>
                <span className={css('status-dot good')} />
                Nothing needs your attention right now.
              </div>
            )}
            <div className={css('tiles kpis')}>
              <Kpi
                label="Users who made something"
                value={number(now.active_users)}
                delta={<Change now={now.active_users} before={before.active_users} days={days} />}
                trend={series.active_users}
                note={`in the last ${days} days`}
              />
              <Kpi
                label="Items made"
                value={number(now.items)}
                delta={<Change now={now.items} before={before.items} days={days} />}
                trend={series.videos.map((v, i) => v + series.images[i])}
              />
              <Kpi
                label="Jobs that succeeded"
                value={now.success_rate == null ? 'No jobs' : now.success_rate + '%'}
                delta={<Change now={now.success_rate} before={before.success_rate} days={days} />}
                trend={series.done}
              />
              <Kpi
                label="GPU time"
                value={span(now.gpu_seconds)}
                delta={<Change now={now.gpu_seconds} before={before.gpu_seconds} days={days} />}
                trend={series.gpu_minutes}
              />
              <Kpi
                label="Credits spent"
                value={number(now.credits)}
                delta={<Change now={now.credits} before={before.credits} days={days} />}
                trend={series.credits}
              />
            </div>
            <div className={css('stat-row')}>
              {(
                [
                  ['Jobs', number(now.jobs)],
                  ['Failed', number(now.failed)],
                  ['Average wait in queue', span(now.avg_wait) || '0 s'],
                  ['Average render time', span(now.avg_run) || 'none yet'],
                  ['New accounts', number(now.signups)],
                  ['All users', number(o.totals.users)],
                  ['All library items', number(o.totals.items)],
                  ['Credits held by users', number(o.totals.credits_held)],
                ] as const
              ).map(([k, v]) => (
                <div key={k}>
                  <span className="muted">{k}</span>
                  <b>{v}</b>
                </div>
              ))}
            </div>
            <div className={css('grid-2')}>
              <Online people={o.online} />
              <Signups s={o.signups} />
            </div>
            <div className={css('grid-2')}>
              <QueueCard q={o.queue} server={o.server} />
              <Activity rows={o.activity} />
            </div>
            <Earnings money={o.economics} days={days} />
            <div className={css('grid-2')}>
              <ChartCard
                title="Items made per day"
                subtitle="Finished videos and images"
                spec={{
                  labels,
                  format: number,
                  series: [
                    { name: 'Videos', color: 'var(--series-1)', values: series.videos },
                    { name: 'Images', color: 'var(--series-2)', values: series.images },
                  ],
                }}
              />
              <ChartCard
                title="Jobs per day by result"
                subtitle="By the day the job was added"
                spec={{
                  labels,
                  format: number,
                  series: [
                    { name: 'Done', color: 'var(--series-1)', values: series.done },
                    { name: 'Failed', color: 'var(--status-critical)', values: series.failed },
                    { name: 'Cancelled', color: 'var(--chart-neutral)', values: series.cancelled },
                  ],
                }}
              />
              <ChartCard
                title="GPU minutes per day"
                subtitle="Render time of finished jobs"
                spec={{
                  labels,
                  format: (v) => number(Math.round(v * 10) / 10),
                  series: [{ name: 'GPU minutes', color: 'var(--series-1)', values: series.gpu_minutes }],
                }}
              />
              <ChartCard
                title="Credits spent per day"
                subtitle="Charges minus refunds"
                spec={{
                  labels,
                  format: number,
                  series: [{ name: 'Credits', color: 'var(--series-1)', values: series.credits }],
                }}
              />
            </div>
            <Rankings o={o} />
          </>
        );
      }}
    </Loaded>
  );
}
