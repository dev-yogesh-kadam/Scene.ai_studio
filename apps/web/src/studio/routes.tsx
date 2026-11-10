// The address → page table of the studio. Each page's code is fetched the first time it is opened, not with the app:
// the canvas and the agent are most of it. The addresses are the classic studio's, one for one.

import { useEffect, type ComponentType } from 'react';
import { Navigate, type RouteObject } from 'react-router';
import { AppShell } from './layout/AppShell';
import { LANDING } from './pages';
import { PlaceGate } from './place';
import { SessionGate, consoleAddress, useUser } from './session';
import { SignedOut } from './SignedOut';
import { LinkClicks } from '../common/LinkClicks';

type PageModule = { default: ComponentType };

/** A page fetched when first opened. `place`: it opens on the project or module its address names (/canvas/PRJ...). */
const page = (load: () => Promise<PageModule>, place = false): Pick<RouteObject, 'lazy'> => ({
  lazy: async () => {
    const Page = (await load()).default;
    return {
      Component: place
        ? () => (
            <PlaceGate>
              <Page />
            </PlaceGate>
          )
        : Page,
    };
  },
});

const home = () => import('./pages/home/HomePage');
const projects = () => import('./pages/projects/ProjectsPage');
const project = () => import('./pages/project/ProjectPage');
const analytics = () => import('./pages/analytics/AnalyticsPage');
// The canvas and its agent are two files, asked for together: the agent is not in the canvas's file, nor on any other page.
export const agentModule = () => import('./features/agent/AgentTabs');
const canvas = () => Promise.all([import('./pages/canvas/CanvasPage'), agentModule()]).then(([page]) => page);
const create = () => import('./pages/create/CreatePage');
const library = () => import('./pages/library/LibraryPage');
const skills = () => import('./pages/skills/SkillsPage');
const settings = () => import('./pages/settings/SettingsPage');
const guide = () => import('./pages/guide/GuidePage');

/** Where the admin console used to be (/admin), in an old link: it is a site of its own now. */
function AdminMoved() {
  const user = useUser();
  useEffect(() => {
    if (user.console) location.replace(consoleAddress(user));
  }, [user]);
  return user.console ? null : <Navigate to={LANDING} replace />;
}

function Root() {
  return (
    <>
      <LinkClicks />
      <SessionGate signedIn={<AppShell />} signedOut={(onSignedIn) => <SignedOut onSignedIn={onSignedIn} />} />
    </>
  );
}

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <Root />,
    children: [
      { index: true, element: <Navigate to={LANDING} replace /> },
      { path: 'home', ...page(home) },
      { path: 'projects', ...page(projects) },
      { path: 'library', ...page(library) },
      { path: 'skills', ...page(skills) },
      { path: 'guide', ...page(guide) },
      { path: 'create', ...page(create) },
      { path: 'settings', ...page(settings) },
      { path: 'project/*', ...page(project, true) },
      { path: 'analytics/*', ...page(analytics, true) },
      { path: 'canvas/*', ...page(canvas, true) },
      { path: 'admin', element: <AdminMoved /> },
      // The component catalogue, in development only: the production build has neither the route nor the page.
      ...(import.meta.env.DEV ? [{ path: 'dev/components', ...page(() => import('./pages/dev/ComponentsPage')) }] : []),
      { path: '*', element: <Navigate to={LANDING} replace /> },
    ],
  },
];
