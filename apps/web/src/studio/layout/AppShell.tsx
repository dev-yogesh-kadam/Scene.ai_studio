// The studio around every page (the classic showApp): on Home, All projects and Library the pages are in a sidebar;
// elsewhere in a dropdown from the logo at the top left, beside where you are (Projects › Name). The account
// (settings, theme, signing out) is in one from your name at the top right, beside the Guide and the balance.

import { useEffect, useRef, useState, type ReactNode, type RefObject } from 'react';
import { Link, Outlet, useLocation } from 'react-router';
import { CreditMark, Icon } from '../../common/components/Icon/Icon';
import { Segmented } from '../../common/components/Segmented';
import { tabTitle } from '../../common/format';
import { THEMES, useAppearance } from '../../common/hooks/useAppearance';
import { useJobs, useStudioLive } from '../live';
import { PAGES, SIDEBAR_PAGES } from '../pages';
import { pageOf } from '../place';
import { consoleAddress, useSession } from '../session';
import { Crumbs, CrumbsProvider, useTrailState } from './crumbs';
import { Announcer } from './Announcer';
import { Announcement, UpdateBar, ViewingBar } from './ShellBars';
import { classesOf } from '../../common/cx';
import css0 from '../../common/components/Icon/Icon.module.css';
import css1 from '../../common/components/Shared.module.css';
import css2 from '../../common/components/Shared2.module.css';
import css3 from '../../common/components/Shared3.module.css';
import css4 from '../../common/components/Shared4.module.css';
import css5 from '../../common/components/Spill.module.css';
import css6 from '../../common/landing/Landing2.module.css';
import css7 from '../../console/ConsoleShell.module.css';
import css8 from './AppShell.module.css';
import css9 from './AppShell2.module.css';
import css10 from './crumbs.module.css';
import css11 from '../pages/guide/GuidePage.module.css';
import css12 from '../pages/projects/projects.module.css';
const css = classesOf(css0, css1, css2, css3, css4, css5, css6, css7, css8, css9, css10, css11, css12);

type Open = 'pages' | 'account' | null;

export function AppShell() {
  useStudioLive();
  const location = useLocation();
  const at = pageOf(location.pathname);
  const narrow = useNarrow();
  const { trail, setTrail } = useTrailState();
  const [chosen, setOpen] = useState<Open>(null);
  const [seenPath, setSeenPath] = useState(location.pathname);
  const pagesButton = useRef<HTMLButtonElement>(null);
  const accountButton = useRef<HTMLButtonElement>(null);
  const pagesMenu = useRef<HTMLDivElement>(null);
  const accountMenu = useRef<HTMLDivElement>(null);
  const railed = SIDEBAR_PAGES.includes(at) && !narrow;
  // Moving to a page closes the menus; with the sidebar shown the pages' dropdown has nothing to open.
  if (seenPath !== location.pathname) {
    setSeenPath(location.pathname);
    setOpen(null);
  }
  const open: Open = railed && chosen === 'pages' ? null : chosen;
  const active = useJobs().filter((j) => j.status === 'queued' || j.status === 'running').length;

  useDropdown(
    open,
    setOpen,
    open === 'pages' ? pagesMenu : accountMenu,
    open === 'pages' ? pagesButton : accountButton,
  );
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);

  const toggle = (which: Open) => (e: React.MouseEvent) => {
    e.stopPropagation();
    setOpen((o) => (o === which ? null : which));
  };

  const pagesList = (inMenu: boolean) => <PagesList active={active} inMenu={inMenu} onPick={() => setOpen(null)} />;
  return (
    <CrumbsProvider onTrail={setTrail}>
      <div
        className={css('shell ' + (railed ? 'railed' : 'compact') + (at === '/canvas' ? ' on-canvas' : ''))}
        data-layout={railed ? 'railed' : 'compact'}
      >
        <div className={css('app-menu-wrap')}>
          <button
            ref={pagesButton}
            type="button"
            className={css('app-menu-button')}
            aria-haspopup="menu"
            aria-expanded={open === 'pages'}
            title="Menu"
            aria-label="Open the menu"
            onClick={toggle('pages')}
          >
            <img src="/img/logo.svg?v=clapper" alt="" />
            <Icon name="chevron" />
            <span className={css('app-menu-badge' + (active ? '' : ' hidden'))} aria-hidden="true" />
          </button>
          <Crumbs trail={trail} />
          <div
            ref={pagesMenu}
            className={css('app-menu' + (open === 'pages' ? '' : ' hidden'))}
            role="menu"
            aria-label="Pages"
          >
            {!railed && pagesList(true)}
          </div>
        </div>
        <aside className={css('sidebar')} aria-label="Scene.ai">
          {railed && (
            <>
              <Link className={css('sidebar-brand')} to="/home" aria-label="Scene.ai: Home">
                <img src="/img/logo.svg?v=clapper" alt="" />
                <b>Scene.ai</b>
              </Link>
              {pagesList(false)}
            </>
          )}
        </aside>
        <div className={css('topbar-right')}>
          <Link className={css('top-btn')} to="/guide">
            <Icon name="book" />
            Guide
          </Link>
          <CreditBadge />
          <div className={css('account-wrap')}>
            <WhoChip buttonRef={accountButton} open={open === 'account'} onClick={toggle('account')} />
            <AccountMenu menuRef={accountMenu} open={open === 'account'} onPick={() => setOpen(null)} />
          </div>
        </div>
        {/* A new page settles in, rising a few pixels as it appears: only moving to a page does this. */}
        {/* the canvas fills the page: no margin round it, nothing scrolls */}
        <main className={css(at === '/canvas' ? 'view entering full' : 'view entering')} key={location.pathname}>
          <PageTitle at={at} />
          <Outlet />
        </main>
      </div>
      <UpdateBar />
      <Announcement />
      <ViewingBar />
      <Announcer />
    </CrumbsProvider>
  );
}

/** The name of the page on the browser tab, set before the page's own (a project's canvas puts its name there). */
function PageTitle({ at }: { at: string }) {
  useEffect(() => {
    tabTitle(PAGES.find((p) => p.path === at)?.label);
  }, [at]);
  return null;
}

/** The pages and the queue: in the sidebar or the dropdown. */
function PagesList({ active, inMenu, onPick }: { active: number; inMenu: boolean; onPick: () => void }) {
  const location = useLocation();
  const at = PAGES.find((p) => p.path === pageOf(location.pathname));
  const shown = PAGES.filter((p) => !p.under && !p.menu);
  return (
    <>
      <nav className={css('nav')} aria-label="Pages" role={inMenu ? 'group' : undefined}>
        {shown.map((p, i) => (
          <PageLink key={p.path} page={p} lit={p.path === (at?.under || at?.path)} inMenu={inMenu} onPick={onPick}>
            {p.group && p.group !== shown[i - 1]?.group ? <div className={css('nav-label')}>{p.group}</div> : null}
          </PageLink>
        ))}
      </nav>
      <div className={css('menu-sep')} />
      {/* Says that something is being made; the whole queue is in the admin console. */}
      <span className={css('working' + (active ? '' : ' hidden'))}>
        <i className={css('cell-mark stepping')} />
        {active === 1 ? '1 job in the queue' : `${active} jobs in the queue`}
      </span>
    </>
  );
}

function PageLink({
  page,
  lit,
  inMenu,
  onPick,
  children,
}: {
  page: (typeof PAGES)[number];
  lit: boolean;
  inMenu: boolean; // in the dropdown, a menu's item; on the sidebar, a link
  onPick: () => void;
  children?: ReactNode;
}) {
  return (
    <>
      {children}
      <Link
        to={page.path}
        role={inMenu ? 'menuitem' : undefined}
        aria-current={lit ? 'page' : undefined}
        className={css(lit ? 'on' : '')}
        onClick={onPick}
      >
        {page.icon && <Icon name={page.icon} />}
        <span className="grow">{page.label}</span>
      </Link>
    </>
  );
}

function CreditBadge() {
  const { user } = useSession();
  return (
    <div className={css('credit-badge')} title="Credits pay for generations. An admin can add more.">
      <CreditMark />
      <b>{Number(user.credits ?? 0).toLocaleString()}</b>
      {Number(user.credits) === 1 ? 'credit' : 'credits'}
    </div>
  );
}

function WhoChip({
  buttonRef,
  open,
  onClick,
}: {
  buttonRef: RefObject<HTMLButtonElement | null>;
  open: boolean;
  onClick: (e: React.MouseEvent) => void;
}) {
  const { user } = useSession();
  return (
    <button
      ref={buttonRef}
      type="button"
      className={css('who-chip')}
      aria-haspopup="menu"
      aria-expanded={open}
      onClick={onClick}
    >
      <span className={css('avatar')} aria-hidden="true">
        {(user.name[0] || '?').toUpperCase()}
      </span>
      <span className={css('who-name')}>{user.name}</span>
      <span className={css('unseen')}>: your account</span>
    </button>
  );
}

function AccountMenu({
  menuRef,
  open,
  onPick,
}: {
  menuRef: RefObject<HTMLDivElement | null>;
  open: boolean;
  onPick: () => void;
}) {
  const { user, signOut } = useSession();
  const appearance = useAppearance();
  const location = useLocation();
  const settings = PAGES.filter((p) => p.menu);
  return (
    <div
      ref={menuRef}
      className={css('app-menu account-menu' + (open ? '' : ' hidden'))}
      role="menu"
      aria-label="Account"
    >
      <div className={css('app-menu-who')}>
        <div className={css('avatar')}>{(user.name[0] || '?').toUpperCase()}</div>
        <div className={css('who')}>
          <b>{user.name}</b>
          <span>{user.email}</span>
        </div>
      </div>
      <div className={css('menu-sep')} />
      {settings.map((p) => (
        <Link
          key={p.path}
          to={p.path}
          role="menuitem"
          className={css(pageOf(location.pathname) === p.path ? 'on' : '')}
          onClick={onPick}
        >
          {p.icon && <Icon name={p.icon} />}
          <span className="grow">{p.label}</span>
        </Link>
      ))}
      {/* The admin console is a site of its own, on its own port and sign-in: it opens in a tab of its own. */}
      {user.console && (
        <a href={consoleAddress(user)} target="_blank" rel="noopener" role="menuitem" onClick={onPick}>
          <Icon name="shield" />
          <span className="grow">Admin console</span>
        </a>
      )}
      <div className={css('menu-row')}>
        Theme
        <Segmented choices={THEMES} current={appearance.theme} onPick={appearance.setTheme} />
      </div>
      <button role="menuitem" className={css('menu-item')} onClick={() => void signOut()}>
        <Icon name="logout" />
        Sign out
      </button>
    </div>
  );
}

/** One dropdown open at a time; a click outside it or Escape closes it (Escape gives the focus back to its button).
 *  Opening one puts the focus on its first item. */
function useDropdown(
  open: Open,
  setOpen: (o: Open) => void,
  panel: RefObject<HTMLElement | null>,
  button: RefObject<HTMLElement | null>,
) {
  useEffect(() => {
    if (!open) return;
    const items = panel.current ? [...panel.current.getElementsByTagName('*')] : [];
    (items.find((n) => n.tagName === 'A' || n.tagName === 'BUTTON') as HTMLElement | undefined)?.focus();
    const close = (e: Event) => {
      if (e.type === 'keydown' && (e as KeyboardEvent).key !== 'Escape') return;
      if (e.type === 'click' && panel.current && e.composedPath().includes(panel.current)) return;
      setOpen(null);
      if (e.type === 'keydown') button.current?.focus();
    };
    window.addEventListener('click', close);
    window.addEventListener('keydown', close);
    return () => {
      window.removeEventListener('click', close);
      window.removeEventListener('keydown', close);
    };
  }, [open, setOpen, panel, button]);
}

/** Below 860px the sidebar folds into the dropdown. */
function useNarrow() {
  const [narrow, setNarrow] = useState(() => window.matchMedia('(max-width: 860px)').matches);
  useEffect(() => {
    const query = window.matchMedia('(max-width: 860px)');
    const change = () => setNarrow(query.matches);
    query.addEventListener('change', change);
    return () => query.removeEventListener('change', change);
  }, []);
  return narrow;
}
