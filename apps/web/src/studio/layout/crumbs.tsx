// Where you are, beside the logo: the page, or the page it is reached from and its own name. A page that knows more,
// such as a project's, says so with useCrumbs([{label, href?}]) (the classic page sent a "scene:crumbs" event).

import { Fragment, createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router';
import { PAGES } from '../pages';
import { pageOf } from '../place';
import { classesOf } from '../../common/cx';
import css0 from './crumbs.module.css';
const css = classesOf(css0);

export type Crumb = { label: string; href?: string };

const CrumbsContext = createContext<(trail: Crumb[] | null) => void>(() => {});

export function CrumbsProvider({ children, onTrail }: { children: ReactNode; onTrail: (t: Crumb[] | null) => void }) {
  return <CrumbsContext.Provider value={onTrail}>{children}</CrumbsContext.Provider>;
}

/** A page's own trail, while it is open. */
export function useCrumbs(trail: Crumb[] | null) {
  const setTrail = useContext(CrumbsContext);
  const key = JSON.stringify(trail);
  useEffect(() => {
    setTrail(trail);
    return () => setTrail(null);
    // the trail is compared by what it says, not by which array it is
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, setTrail]);
}

export function useTrailState() {
  const [trail, setTrail] = useState<Crumb[] | null>(null);
  return { trail, setTrail };
}

export function Crumbs({ trail }: { trail: Crumb[] | null }) {
  const location = useLocation();
  const at = PAGES.find((p) => p.path === pageOf(location.pathname));
  const parent = at?.under ? PAGES.find((p) => p.path === at.under) : undefined;
  const steps: Crumb[] =
    trail ||
    (parent
      ? [{ label: parent.crumb || parent.label || '', href: parent.path }]
      : at?.label
        ? [{ label: at.crumb || at.label }]
        : []);
  return (
    <nav className={css('crumbs' + (steps.length ? '' : ' hidden'))} aria-label="Where you are">
      {steps.map((s, i) => (
        <Fragment key={i}>
          {i > 0 && (
            <span className={css('crumb-sep')} aria-hidden="true">
              ›
            </span>
          )}
          {s.href && i < steps.length - 1 ? <Link to={s.href}>{s.label}</Link> : <b>{s.label}</b>}
        </Fragment>
      ))}
    </nav>
  );
}
