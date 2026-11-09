// Page addresses: /library, /canvas and so on, not #/library. `go` moves to one without reloading the page and tells
// whoever is listening (the router) with a "scene:route" event; the back and forward buttons do the same.

import { api } from './api.js';

export const here = () => location.pathname.replace(/\/+$/, '') || '/';

export function go(path, { replace = false } = {}) {
  if (path === location.pathname + location.search) return;
  history[replace ? 'replaceState' : 'pushState'](null, '', path);
  window.dispatchEvent(new Event('scene:route'));
}

// Links inside the studio are plain <a href="/library">: a click on one (not with a modifier key, not to a file or the
// API) is a move within the page, not a new load.
export function linkClicks() {
  window.addEventListener('popstate', () => window.dispatchEvent(new Event('scene:route')));
  document.addEventListener('click', (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const link = e.target.closest && e.target.closest('a[href]');
    if (!link || link.target || link.hasAttribute('download')) return;
    const href = link.getAttribute('href');
    if (!href.startsWith('/') || href.startsWith('//') || /^\/(api|assets|v)\//.test(href) || /\.[a-z0-9]+$/i.test(href.split('?')[0])) return;
    e.preventDefault();
    go(href);
  });
}

// An address from before (/#/library) is moved to the new one (/library).
export function oldAddress() {
  if (location.hash.startsWith('#/')) history.replaceState(null, '', location.hash.slice(1));
}

// Where an admin's browser finds the admin console, a site of its own: the address the studio was told, or its port on
// the host the studio was opened at.
export function consoleAddress(user) {
  return user.console.url || `${location.protocol}//${location.hostname}:${user.console.port}`;
}

// ---------------------------------------------------------------- a project's places by their ids
// A project's pages show its id and its module's, like /canvas/PRJ7fK2mQ9xLt4wA/module/MODa83JdpQ0zR1cX: a link that
// names one place, for every tab and anyone it is sent to. The page is the first part (/canvas), the ids the rest.

export const pageOf = () => '/' + (here().split('/')[1] || '');

// {project, module}: the ids the address names ('' for none).
export function placeIds() {
  const parts = here().split('/');
  return { project: parts[2] || '', module: parts[3] === 'module' ? parts[4] || '' : '' };
}

// The address of `to` (/canvas, /project, /analytics) for a project, or a module of one. `p` is a project
// row ({ref, parent_ref}) or a module of a project's page with its project's ref; the project's own canvas has no
// module part.
export function placePath(to, p, projectRef = '') {
  if (!p || !p.ref) return to;
  const top = p.parent_ref || projectRef || p.ref;
  const module = to === '/canvas' && p.ref !== top;
  return to + '/' + top + (module ? '/module/' + p.ref : '');
}

// The id of the project or module the address names, by asking the studio for its ids; with none, the one worked in
// last (0 = all work). Remembered as the one worked in last.
let placed = 0;
export async function placeFromAddress() {
  const ids = placeIds();
  const ref = ids.module || ids.project;
  if (!ref) return Number(localStorage.getItem('scene.project')) || 0;
  const found = await api('/api/refs/' + encodeURIComponent(ref));
  localStorage.setItem('scene.project', found.id);
  placed = found.id;
  return found.id;
}

// The project or module the address names, once the router has looked it up (0 before, or with no id in the address).
export const placeId = () => (placeIds().project ? placed : 0);

// Shows `path` as the address without moving to it (the page is already there).
export function showAddress(path) {
  if (path !== location.pathname) history.replaceState(null, '', path + location.search);
}
