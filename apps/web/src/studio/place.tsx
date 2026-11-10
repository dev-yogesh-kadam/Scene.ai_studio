// A project's places by their ids. A project's pages show its id and its module's, like
// /canvas/PRJ7fK2mQ9xLt4wA/module/MODa83JdpQ0zR1cX: a link that names one place, for every tab and anyone it is sent to.
// The page is the first part (/canvas), the ids the rest. Before the page opens, the id is looked up (/api/refs/{ref});
// with no id in the address, the page opens on the project worked in last.

import { useQuery } from '@tanstack/react-query';
import { createContext, useContext, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router';
import { api } from '../common/api';
import { classesOf } from '../common/cx';
import css0 from '../common/components/Shared2.module.css';
import css1 from './pages/projects/ProjectsPage.module.css';
import { userPrefs } from './userPrefs';
const css = classesOf(css0, css1);

export const here = (path = window.location.pathname) => path.replace(/\/+$/, '') || '/';

/** The page part of an address: /canvas for /canvas/PRJ.../module/MOD... */
export const pageOf = (path?: string) => '/' + (here(path).split('/')[1] || '');

/** {project, module}: the ids the address names ('' for none). */
export function placeIds(path?: string) {
  const parts = here(path).split('/');
  return { project: parts[2] || '', module: parts[3] === 'module' ? parts[4] || '' : '' };
}

type Row = { ref?: string; parent_ref?: string | null };

/** The address of `to` (/canvas, /project, /analytics) for a project, or a module of one. `p` is a project row
 *  ({ref, parent_ref}) or a module of a project's page with its project's ref; the project's own canvas has no module
 *  part. */
export function placePath(to: string, p: Row | null | undefined, projectRef = '') {
  if (!p || !p.ref) return to;
  const top = p.parent_ref || projectRef || p.ref;
  const module = to === '/canvas' && p.ref !== top;
  return to + '/' + top + (module ? '/module/' + p.ref : '');
}

/** The project or module worked in last (0 = all work), kept in this browser. */
export const lastPlace = () => userPrefs.studio().project || 0;

const PlaceContext = createContext(0);

/** The id of the project or module the address names, or the one worked in last (0 = all work). */
export const usePlaceId = () => useContext(PlaceContext);

/** Looks up the place the address names before drawing the page; says so (with a way back) when there is none. */
export function PlaceGate({ children }: { children: ReactNode }) {
  const location = useLocation();
  const ids = placeIds(location.pathname);
  const ref = ids.module || ids.project;
  const found = useQuery({
    queryKey: ['ref', ref],
    queryFn: () => api<{ id: number }>('/api/refs/' + encodeURIComponent(ref)),
    enabled: !!ref,
    staleTime: Infinity,
    retry: false,
  });
  if (!ref) return <PlaceContext.Provider value={lastPlace()}>{children}</PlaceContext.Provider>;
  if (found.isError) {
    return (
      <div className={css('empty')}>
        <p>{found.error.message}</p>
        <Link className="btn" to="/projects">
          All projects
        </Link>
      </div>
    );
  }
  if (!found.data) return null;
  userPrefs.setStudio({ project: found.data.id }); // remembered as the one worked in last
  return (
    <PlaceContext.Provider value={found.data.id} key={found.data.id}>
      {children}
    </PlaceContext.Provider>
  );
}
