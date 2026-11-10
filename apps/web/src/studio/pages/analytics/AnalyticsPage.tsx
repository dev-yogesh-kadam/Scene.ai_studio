// A project's analytics (/analytics/<project's id>): what it spent and made in a period, by day and kind of thing made,
// and by module. Reached from the project's page; Back to project returns there.

import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { api } from '../../../common/api';
import { ColumnChart } from '../../../common/components/Charts';
import { Icon } from '../../../common/components/Icon/Icon';
import { Segmented } from '../../../common/components/Segmented';
import { tabTitle } from '../../../common/format';
import { prefs } from '../../../common/prefs';
import { useCrumbs } from '../../layout/crumbs';
import { placePath, usePlaceId } from '../../place';
import s from './AnalyticsPage.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import { ErrorBanner, Skeleton } from '../../../common/components/States';
const css = classesOf(css0, css1);

const PERIODS = [
  { id: 'today', label: 'Today' },
  { id: '7', label: 'Last 7 days' },
  { id: '30', label: 'Last 30 days' },
  { id: 'month', label: 'This month' },
];
// One colour per kind of thing made, the same in the chart, the legend and a module's breakdown.
const COLOURS: Record<string, string> = {
  video: '#a8a8b2',
  voiceover: '#e5534b',
  music: '#e9a23b',
  image: '#3fb950',
  motion: '#a371f7',
  edit: '#2bb3a6',
  llm: '#3987e5',
};
const number = (n: number | null | undefined) => Number(n || 0).toLocaleString();
const day = (t: number) =>
  new Date(t * 1000).toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' });

type Kind = { id: string; label: string; credits: number; generations: number };
type ModuleRow = {
  id: number;
  number: number;
  name: string;
  first?: number | null;
  generations: number;
  asset_types: number;
  credits: number;
  types: Record<string, { credits: number; generations: number }>;
};
type Analytics = {
  project: { id: number; ref: string; name: string; parent_ref?: string | null };
  start: number;
  end: number;
  spend: number;
  spend_before?: number;
  change: number | null;
  generations: number;
  active_modules: number;
  contributors: number;
  owner: string;
  types: Kind[];
  days: string[];
  daily: Record<string, number>[];
  modules: ModuleRow[];
};

export default function AnalyticsPage() {
  const id = usePlaceId() || Number(new URLSearchParams(location.search).get('id')) || 0;
  const [period, setPeriod] = useState(() => prefs.get('scene.analytics.period', '7'));
  const query = useQuery({
    queryKey: ['analytics', id, period],
    queryFn: () => api<Analytics>(`/api/projects/${id}/analytics?period=${period}`),
  });
  const d = query.data;
  useCrumbs(
    d
      ? [
          { label: 'Projects', href: '/projects' },
          { label: d.project.name, href: placePath('/project', d.project) },
          { label: 'Analytics' },
        ]
      : null,
  );
  useEffect(() => {
    if (!d) return;
    document.title = `Analytics · ${d.project.name} · Scene.ai`;
    const path = placePath('/analytics', d.project); // a module's address, or an old one, shows the project's id
    if (path !== location.pathname) history.replaceState(history.state, '', path + location.search);
    return () => tabTitle('Analytics');
  }, [d]);

  return (
    <div className={s['an-page']}>
      <Link className={s['an-back']} to={d ? placePath('/project', d.project) : '/project?id=' + id}>
        <Icon name="back" />
        Back to project
      </Link>
      <div className={s['an-head']}>
        <h1>Analytics</h1>
        <div className={s['an-tools']}>
          <div>
            <Segmented
              choices={PERIODS}
              current={period}
              onPick={(p) => {
                setPeriod(p);
                prefs.set('scene.analytics.period', p);
              }}
            />
          </div>
          <a className="btn" download="" href={`/api/projects/${id}/analytics.csv?period=${period}`}>
            Export CSV
          </a>
        </div>
      </div>
      <div className={s['an-body']}>
        {query.isError ? (
          <>
            <ErrorBanner error={query.error} onRetry={() => void query.refetch()} />
            <Link className="btn" to="/projects">
              All projects
            </Link>
          </>
        ) : !d ? (
          <Skeleton count={4} shape="line" />
        ) : (
          <>
            <div className={s['an-showing'] + ' muted small'}>
              <Icon name="clock" />
              {'Showing '}
              <b>{`${day(d.start)} – ${day(d.end)}`}</b>
            </div>
            <Tiles d={d} />
            <Daily d={d} />
            <Modules d={d} />
          </>
        )}
      </div>
    </div>
  );
}

function Tiles({ d }: { d: Analytics }) {
  const change = d.change == null ? null : d.change;
  return (
    <div className={s['an-tiles']}>
      <div className={s['an-tile']}>
        <span className={s['an-label']}>Project spend</span>
        <div>
          <b className={s['an-value']}>{number(d.spend)}</b>
          <span className="muted"> credits</span>
        </div>
        <span className={'small ' + (change == null ? 'muted' : change > 0 ? s['an-up'] : s['an-down'])}>
          {change == null
            ? d.spend_before
              ? ''
              : 'Nothing spent the period before'
            : `${change > 0 ? '↑' : '↓'} ${Math.abs(change)}% vs previous period`}
        </span>
      </div>
      <div className={s['an-tile']}>
        <span className={s['an-label']}>Generations</span>
        <div>
          <b className={s['an-value']}>{number(d.generations)}</b>
          <span className="muted">{d.generations === 1 ? ' generation' : ' generations'}</span>
        </div>
        <span className="small muted">{`${d.active_modules} active ${d.active_modules === 1 ? 'module' : 'modules'}`}</span>
      </div>
      <div className={s['an-tile']}>
        <span className={s['an-label']}>Contributors</span>
        <div>
          <b className={s['an-value']}>{number(d.contributors)}</b>
          <span className="muted">{d.contributors === 1 ? ' person' : ' people'}</span>
        </div>
        <span className="small muted">{d.owner}</span>
      </div>
    </div>
  );
}

function Legend({ kind, credits, extra }: { kind: Kind; credits: number; extra: string }) {
  return (
    <div className={s['an-legend-row']}>
      <span className={s['an-dot']} style={{ background: COLOURS[kind.id] }} />
      <span className="grow">{kind.label}</span>
      <b>{number(credits)}</b>
      <span className="muted small">{extra}</span>
    </div>
  );
}

function Daily({ d }: { d: Analytics }) {
  const total = d.types.reduce((sum, t) => sum + t.credits, 0);
  const series = d.types
    .filter((t) => t.credits)
    .map((t) => ({ name: t.label, color: COLOURS[t.id], values: d.daily.map((x) => x[t.id]) }));
  return (
    <div className={css('card ' + s['an-daily'])}>
      <div className={s['an-chart']}>
        <h2>Daily spend</h2>
        <p className="muted small">Credits spent across this project, by the kind of thing made.</p>
        {series.length ? (
          <ColumnChart labels={d.days} series={series} format={number} height={220} />
        ) : (
          <div className={s['an-empty']}>No spend in this period yet.</div>
        )}
      </div>
      <div className={s['an-legend']}>
        <h3>Spend by kind</h3>
        {d.types.map((t) => (
          <Legend
            key={t.id}
            kind={t}
            credits={t.credits}
            extra={`${t.generations} gen · ${total ? Math.round((100 * t.credits) / total) : 0}%`}
          />
        ))}
      </div>
    </div>
  );
}

function Modules({ d }: { d: Analytics }) {
  return (
    <section className={s['an-modules']}>
      <h2>Spend by module</h2>
      <p className="muted small">The modules that spent the most first. Open one for what it spent on.</p>
      {d.modules.map((m) => (
        <ModuleSpend key={m.id ?? m.number} d={d} m={m} />
      ))}
    </section>
  );
}

function ModuleSpend({ d, m }: { d: Analytics; m: ModuleRow }) {
  const [opened, setOpened] = useState(false);
  return (
    <div className={s['an-module']}>
      <button className={s['an-row']} aria-expanded={opened} onClick={() => setOpened(!opened)}>
        <span className={s['an-number']}>{String(m.number)}</span>
        <span className={s['an-name']}>
          <b>{m.name}</b>
          <span className="muted small">
            {m.first ? `1st generation: ${day(m.first)} · ${d.owner}` : 'Not generated yet'}
          </span>
        </span>
        <span className={s['an-stat']}>
          <span>Generations</span>
          <b>{number(m.generations)}</b>
        </span>
        <span className={s['an-stat']}>
          <span>Kinds</span>
          <b>{number(m.asset_types)}</b>
        </span>
        <span className={s['an-stat']}>
          <span>Credits</span>
          <b>{number(m.credits)}</b>
        </span>
        <span className={s['an-open']} aria-hidden="true">
          ›
        </span>
      </button>
      <div className={s['an-detail'] + (opened ? '' : ' hidden')}>
        {Object.keys(m.types).length ? (
          d.types
            .filter((t) => m.types[t.id])
            .map((t) => (
              <Legend key={t.id} kind={t} credits={m.types[t.id].credits} extra={`${m.types[t.id].generations} gen`} />
            ))
        ) : (
          <p className="muted small">Nothing spent or made in this period.</p>
        )}
      </div>
    </div>
  );
}
