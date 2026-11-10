// The studio's pages, as the menu and the breadcrumbs know them. `group` is the heading a page sits under in the menu.
// A page with `under` has no menu entry of its own: it is reached from the page it names, which stays lit while it is
// open. A page with `menu` is listed lower, in the account menu, with the settings and signing out.

import type { IconName } from '../common/components/Icon/Icon';

export type PageInfo = {
  path: string;
  label?: string;
  crumb?: string;
  icon?: IconName;
  group?: string;
  under?: string;
  menu?: boolean;
};

export const PAGES: PageInfo[] = [
  { path: '/home', label: 'Home', icon: 'home' },
  { path: '/projects', label: 'All projects', crumb: 'Projects', icon: 'folder', group: 'Workspace' },
  { path: '/library', label: 'Library', icon: 'grid', group: 'Workspace' },
  { path: '/skills', label: 'Skills', icon: 'skill', group: 'Workspace' },
  { path: '/guide', label: 'Guide', icon: 'book', group: 'Help' },
  { path: '/create', under: '/home' },
  { path: '/project', under: '/projects' },
  { path: '/analytics', label: 'Analytics', under: '/projects' },
  { path: '/canvas', under: '/projects' },
  { path: '/settings', label: 'Settings', icon: 'sliders', menu: true },
];

/** Where signing in lands, and where an address the studio has no page for goes. */
export const LANDING = '/projects';

/** The pages that show the menu in full down the left, as a sidebar; every other page has it in the dropdown under
 *  the logo, beside where you are. A narrow screen always uses the dropdown. */
export const SIDEBAR_PAGES = ['/home', '/projects', '/library'];
