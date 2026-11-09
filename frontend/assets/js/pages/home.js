// The Home page: a bar to start something, the projects worked on lately, and the best work made on the studio, as an
// admin picked it for everyone (the console's Home page section). Until anything is picked, the user's own latest work.

import { api } from '../api.js';
import { el, segmented, ago, initials, still, spill } from '../dom.js';
import { store, subscribe } from '../store.js';
import { openViewer } from '../components/media.js';
import { composer } from '../components/composer.js';
import { go, placePath } from '../nav.js';

const RECENT = 8;    // projects shown
const MADE = 60;     // finished items shown

export function render(view) {
  let kind = '';     // '' = everything, or 'video' / 'image'
  let section = '';  // the showcase's tab: '' = All, or a section's name
  let picked = null; // the showcase, {sections, items}, once asked for; its items empty when nothing is picked
  let asked = 0;     // the newest library request; older answers are dropped
  const queued = el('p', { class: 'notice ok home-note' });
  const dock = composer({ onQueued: () => {
    // The job is filed under no project, so open the canvas on everything, not on the last project.
    queued.replaceChildren('Added to the queue. ',
      el('a', { href: '/canvas', onclick: () => localStorage.setItem('scene.project', '') }, 'Watch it on the Canvas'));
  } });
  // A prompt typed on the landing page before signing up (pages/landing.js) is waiting in the prompt box, once.
  let waiting = '';
  try { waiting = localStorage.getItem('scene.firstPrompt') || ''; localStorage.removeItem('scene.firstPrompt'); } catch (e) { /* storage off */ }
  if (waiting) dock.setPrompt(waiting);
  const recent = el('section', { class: 'home-section hidden' });
  const filter = el('div');
  const grid = el('div', { class: 'made-grid' });
  const madeTitle = el('h2', {}, 'Created on Scene.ai');
  const libraryLink = el('a', { class: 'btn small quiet', href: '/library' }, 'Open library');
  // The showcase's videos play, without sound, while they are on screen, and stop once scrolled away.
  const playing = new IntersectionObserver((entries) => entries.forEach((e) => {
    const video = e.target;
    if (e.isIntersecting) { video.preload = 'auto'; video.play().catch(() => {}); } else video.pause();
  }), { rootMargin: '120px 0px' });
  const light = spill();   // the newest picture or video lights the top of the page

  view.replaceChildren(
    light.node,
    el('div', { class: 'home-hero' }, el('h1', {}, 'What are you making today?')),
    el('div', { class: 'home-bar' }, dock.node, queued),
    recent,
    el('section', { class: 'home-section' },
      el('div', { class: 'section-head' }, madeTitle, filter, libraryLink),
      grid));

  const openProject = (project) => {
    if (project.modules) return go(placePath('/project', project));   // a project with modules opens on its page, to pick one
    localStorage.setItem('scene.project', project.id);
    go(placePath('/canvas', project));
  };

  const cover = (id, itemKind, name) => still(`/api/library/${id}/file`, itemKind, name);

  // Recent projects: left out completely until the user has made one.
  async function drawRecent() {
    const projects = (await api('/api/projects')).projects.filter((p) => !p.parent_id)
      .sort((a, b) => (b.updated || b.created) - (a.updated || a.created)).slice(0, RECENT);
    recent.classList.toggle('hidden', !projects.length);
    if (!projects.length) return;
    recent.replaceChildren(
      el('div', { class: 'section-head' }, el('h2', {}, 'Recent projects'),
        el('a', { class: 'btn small quiet', href: '/projects' }, 'See all')),
      el('div', { class: 'project-grid' }, projects.map((p) => el('button', { class: 'project', onclick: () => openProject(p) },
        el('div', { class: 'project-cover' }, p.cover_id ? cover(p.cover_id, p.cover_kind, p.name) : initials(p.name)),
        el('b', {}, p.name),
        el('span', { class: 'slate-text' }, [p.items === 1 ? '1 item' : `${p.items} items`, ago(p.updated || p.created)].join(' · '))))));
  }

  // The work an admin picked for every user's Home page, under its sections' tabs.
  function drawShowcase() {
    const tabs = picked.sections.filter((n) => picked.items.some((i) => i.section === n));
    if (section && !tabs.includes(section)) section = '';
    madeTitle.textContent = 'Made on Scene.ai';
    libraryLink.classList.add('hidden');
    filter.replaceChildren(...(tabs.length ? [segmented([{ id: '', label: 'All' }, ...tabs.map((n) => ({ id: n, label: n }))], section,
      (n) => { section = n; drawShowcase(); })] : []));
    const items = picked.items.filter((i) => !section || i.section === section);
    const first = items.find((i) => i.kind !== 'audio');
    light.show(first && first.id, first && first.kind, '/api/showcase');
    playing.disconnect();
    grid.classList.add('made-grid', 'showcase-grid-home');
    grid.replaceChildren(...items.map((item) => {
      const c = item.context || {};
      const url = `/api/showcase/${item.id}/file`;
      const media = item.kind === 'video'
        ? el('video', { src: url, poster: `/api/showcase/${item.id}/poster`, muted: true, loop: true, playsinline: true, preload: 'none', 'aria-label': item.name })
        : el('img', { src: url, alt: item.name, loading: 'lazy', decoding: 'async', draggable: 'false' });
      if (item.kind === 'video') { media.muted = true; playing.observe(media); }
      return el('button', { class: 'made', title: item.name, style: c.width ? `aspect-ratio:${c.width}/${c.height}` : '',
        onclick: () => openViewer(item, { base: '/api/showcase' }) }, media, el('span', {}, item.name));
    }));
  }

  async function drawMade() {
    if (!picked) picked = await api('/api/showcase').catch(() => ({ sections: [], items: [] }));
    if (picked.items.length) return drawShowcase();
    madeTitle.textContent = 'Created on Scene.ai';
    libraryLink.classList.remove('hidden');
    filter.replaceChildren(segmented([{ id: '', label: 'All' }, { id: 'video', label: 'Videos' }, { id: 'image', label: 'Images' }, { id: 'audio', label: 'Audio' }],
      kind, (k) => { kind = k; drawMade().catch(() => {}); }));
    const request = ++asked;
    const items = (await api('/api/library' + (kind ? '?kind=' + kind : ''))).items.slice(0, MADE);
    if (request !== asked) return;
    const newest = items.find((i) => i.kind !== 'audio');
    if (!kind) light.show(newest && newest.id, newest && newest.kind);
    grid.classList.toggle('made-grid', items.length > 0);
    grid.replaceChildren(...(items.length ? items.map((item) => {
      const c = item.context || {};
      return el('button', { class: 'made', title: item.name, style: c.width ? `aspect-ratio:${c.width}/${c.height}` : '',
        onclick: () => openViewer(item, { actions: /^(edit|upload)\//.test(item.workflow) ? []
          : [{ label: 'Re-run', run: (dialog) => { dialog.close(); store.rerun = item; go('/create'); } }] }) },
        cover(item.id, item.kind, item.name), el('span', {}, item.name));
    }) : [el('div', { class: 'empty' }, kind ? 'Nothing of this kind yet.' : 'Nothing made yet. Describe a shot in the bar above and it will appear here.')]));
  }

  const draw = () => Promise.all([drawRecent(), drawMade()]).catch((e) => { grid.replaceChildren(el('p', { class: 'error' }, e.message)); });
  draw();
  // A new result changes the recent projects, and the user's own work when that is what is shown; never the showcase.
  const unsubscribe = subscribe((change) => {
    if (change === 'library') Promise.all([drawRecent(), picked && picked.items.length ? null : drawMade()]).catch(() => {});
  });
  return () => { unsubscribe(); playing.disconnect(); dock.destroy(); };
}
