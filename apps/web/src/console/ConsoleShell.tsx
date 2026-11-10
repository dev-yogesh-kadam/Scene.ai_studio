// The console around its sections: the sidebar with the sections this person's role may open (staff.py on the server;
// the rest are not shown, and are refused there), how many people have the studio open, the queue and the open alerts,
// search (Ctrl+K), and the section itself.

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Link, Navigate, useLocation } from 'react-router';
import { Icon } from '../common/components/Icon/Icon';
import { Segmented } from '../common/components/Segmented';
import { MOTIONS, THEMES, useAppearance } from '../common/hooks/useAppearance';
import { Palette } from './Palette';
import { SECTIONS, type Section } from './sectionList';
import { ConsoleProvider, useConsole, type ConsoleUser } from './sections/shared/context';
import { Toasts } from './Toasts';
import { useConsoleLive } from './useConsoleLive';
import { classesOf } from '../common/cx';
import css0 from '../common/components/Shared.module.css';
import css1 from '../common/components/Shared2.module.css';
import css2 from '../common/components/Shared3.module.css';
import css3 from '../common/components/Shared4.module.css';
import css4 from '../common/components/Spill.module.css';
import css5 from '../common/landing/Landing2.module.css';
import css6 from './ConsoleShell.module.css';
import css7 from './sections/shared/Console.module.css';
import css8 from '../studio/layout/AppShell.module.css';
import css9 from '../studio/layout/AppShell2.module.css';
import css10 from '../studio/layout/crumbs.module.css';
import css11 from '../studio/pages/guide/GuidePage.module.css';
import css12 from '../studio/pages/projects/projects.module.css';
const css = classesOf(css0, css1, css2, css3, css4, css5, css6, css7, css8, css9, css10, css11, css12);

export function ConsoleShell({ user, onSignOut }: { user: ConsoleUser; onSignOut: () => void }) {
  return (
    <ConsoleProvider user={user}>
      <Shell user={user} onSignOut={onSignOut} />
    </ConsoleProvider>
  );
}

function Shell({ user, onSignOut }: { user: ConsoleUser; onSignOut: () => void }) {
  const location = useLocation();
  const appearance = useAppearance();
  const { go } = useConsole();
  const mine = useMemo(() => SECTIONS.filter((s) => !user.sections || user.sections.includes(s.id)), [user.sections]);
  const at = location.pathname.split('/')[1] || '';
  const shown = mine.find((s) => s.id === at);
  const studio = `${window.location.protocol}//${window.location.hostname}:${user.studio.port}`;
  const body = useRef<HTMLDivElement>(null);
  const [searching, setSearching] = useState(false);
  const live = useConsoleLive(shown, body);

  // A section opened: its title, and the page at the top.
  useLayoutEffect(() => {
    if (!shown) return;
    document.title = `${shown.label} · Admin console`;
    window.scrollTo(0, 0);
  }, [shown]);

  useEffect(() => {
    const searchKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setSearching(true);
      }
    };
    document.addEventListener('keydown', searchKey);
    return () => document.removeEventListener('keydown', searchKey);
  }, []);

  if (!shown) return <Navigate to={'/' + (mine[0] || SECTIONS[0]).id} replace />;

  return (
    <div className={css('shell railed console')}>
      <aside className={css('sidebar')} aria-label="Admin console">
        <div className={css('sidebar-brand')}>
          <img src="/img/logo.svg?v=clapper" alt="" />
          <b>Scene.ai</b>
          <span className={css('console-tag')}>{user.role_label || 'Admin'}</span>
        </div>
        <div className={css('app-menu-who')}>
          <div className={css('avatar')}>{(user.name[0] || '?').toUpperCase()}</div>
          <div className={css('who')}>
            <b>{user.name}</b>
            <span>{user.email}</span>
          </div>
        </div>
        <button className={css('menu-item search-item')} onClick={() => setSearching(true)}>
          <Icon name="search" />
          <span className="grow">Search</span>
          <kbd>Ctrl K</kbd>
        </button>
        <nav className={css('nav')} aria-label="Sections">
          {mine.map((s, i) => (
            <SectionLink
              key={s.id}
              section={s}
              lit={s.id === at}
              heading={s.group !== mine[i - 1]?.group}
              alerts={live.alerts}
              queue={live.queue}
            />
          ))}
        </nav>
        <div className={css('menu-sep')} />
        <a href={studio} target="_blank" rel="noopener">
          <Icon name="forward" />
          <span className="grow">Open the studio</span>
        </a>
        <div className={css('menu-row')}>
          Theme
          <Segmented choices={THEMES} current={appearance.theme} onPick={appearance.setTheme} />
        </div>
        <div className={css('menu-row')}>
          Motion
          <Segmented choices={MOTIONS} current={appearance.motion} onPick={appearance.setMotion} />
        </div>
        <button className={css('menu-item')} onClick={onSignOut}>
          <Icon name="logout" />
          Sign out
        </button>
      </aside>
      <main className={css('view')}>
        <div className={css('page-head')}>
          <h1>{shown.label}</h1>
          <LiveCount people={live.people} bump={live.bump} />
        </div>
        <div ref={body} key={shown.id}>
          <shown.Component />
        </div>
      </main>
      {searching && <Palette mine={mine} onClose={() => setSearching(false)} />}
      <Toasts notes={live.notes} onOpen={() => go('system')} onGone={live.dismiss} />
    </div>
  );
}

function SectionLink({
  section: s,
  lit,
  heading,
  alerts,
  queue,
}: {
  section: Section;
  lit: boolean;
  heading: boolean;
  alerts: number;
  queue: { running: number; waiting: number } | null;
}) {
  return (
    <>
      {heading && <div className={css('nav-label')}>{s.group}</div>}
      <Link to={'/' + s.id} className={css(lit ? 'on' : '')}>
        <Icon name={s.icon} />
        <span className="grow">{s.label}</span>
        {s.id === 'system' && alerts > 0 && (
          <span className={css('pill failed')} title="Open alerts">
            {String(alerts)}
          </span>
        )}
        {s.id === 'jobs' && queue && queue.running + queue.waiting > 0 && (
          <span className={css('nav-count')} title={`${queue.running} running, ${queue.waiting} waiting`}>
            {queue.running ? `${queue.running} · ${queue.waiting}` : String(queue.waiting)}
          </span>
        )}
      </Link>
    </>
  );
}

/** How many people have the studio open, kept up to date as they come and go. Several tabs count once. */
function LiveCount({ people, bump }: { people: number | null; bump: number }) {
  return (
    <div
      className={css('live-count' + (bump ? ' bump' : ''))}
      role="status"
      aria-live="polite"
      title="People with the studio open right now. Several tabs count once."
    >
      <span className={css('dot online')} />
      {/* a new key plays the little bump again */}
      <b key={bump}>{people == null ? '…' : people}</b>
      <span className="muted">{people === 1 ? 'person live now' : 'people live now'}</span>
    </div>
  );
}
