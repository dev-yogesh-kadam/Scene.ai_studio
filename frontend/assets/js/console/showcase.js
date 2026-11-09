// The Home page: the best work, picked here, that every user sees under "Made on Scene.ai" (backend/scene/showcase.py).
// Sections of the admin's naming (Shorts & Reels, Microdrama, Ads…) are the tabs over it; the order here is its order.

import { api } from '../api.js';
import { el, icon, segmented, still } from '../dom.js';
import { openViewer } from '../components/media.js';
import { searchBox } from './shared.js';

const BASE = '/api/admin/showcase';
const thumbOf = (item) => still(`${BASE}/${item.key}/file`, item.kind, item.name);

// An item as the studio's viewer reads it (showcase.public on the server).
const viewed = (item) => ({ id: item.key, kind: item.kind, name: item.name, workflow: item.workflow || '', created: item.added,
  settings: { workflow_title: item.workflow_title, ...(item.show_prompt && item.prompt ? { prompt: item.prompt } : {}) },
  context: { width: item.width, height: item.height, duration: item.duration } });

export async function showcase(ctx) {
  const s = ctx.state.showcase = ctx.state.showcase || { section: '' };
  const data = await api(BASE);
  // Every change is saved at once: the sections and the whole order, with each item's name, section and prompt switch.
  const save = (sections = data.sections, items = data.items) => api(BASE, { method: 'PUT', json: {
    sections, items: items.map((i) => ({ key: i.key, name: i.name, section: i.section, show_prompt: i.show_prompt })) } })
    .then(ctx.draw).catch((e) => alert(e.message));
  const move = (list, at, by) => {
    const next = [...list];
    const [moved] = next.splice(at, 1);
    next.splice(Math.max(0, Math.min(next.length, at + by)), 0, moved);
    return next;
  };

  // The sections: each with ← → to order them and × to take it away (its items stay, under All only).
  const fresh = el('input', { type: 'text', class: 'search', placeholder: 'New section, e.g. Microdrama', maxlength: 40,
    onkeydown: (e) => { if (e.key === 'Enter') addSection(); } });
  const addSection = () => { if (fresh.value.trim()) save([...data.sections, fresh.value.trim()]); };
  const sections = el('div', { class: 'card showcase-sections' },
    el('div', { class: 'showcase-sections-head' }, el('b', {}, 'Sections'),
      el('span', { class: 'muted small' }, 'The tabs over the work on the Home page, in this order. "All" is always first.')),
    el('div', { class: 'chips' }, data.sections.map((name, i) => el('span', { class: 'showcase-chip' },
      el('button', { type: 'button', class: 'icon-btn small', title: 'Earlier', disabled: i === 0, onclick: () => save(move(data.sections, i, -1)) }, '←'),
      el('span', {}, name, el('i', { class: 'muted' }, ` · ${data.items.filter((it) => it.section === name).length}`)),
      el('button', { type: 'button', class: 'icon-btn small', title: 'Later', disabled: i === data.sections.length - 1, onclick: () => save(move(data.sections, i, 1)) }, '→'),
      el('button', { type: 'button', class: 'icon-btn small', title: 'Remove the section (its work stays, under All)', onclick: () => {
        if (confirm(`Remove the section "${name}"? Its work stays on the Home page, under All.`)) save(data.sections.filter((x) => x !== name));
      } }, '×'))),
    el('span', { class: 'showcase-new' }, fresh, el('button', { class: 'btn small', onclick: addSection }, 'Add section'))));

  const shown = data.items.filter((i) => !s.section || i.section === s.section);
  const card = (item) => {
    const at = data.items.indexOf(item);
    const name = el('input', { type: 'text', class: 'showcase-name', value: item.name, maxlength: 80, 'aria-label': 'Name',
      onchange: (e) => { if (e.target.value.trim()) { item.name = e.target.value.trim(); save(); } } });
    return el('div', { class: 'showcase-item' },
      el('button', { type: 'button', class: 'showcase-thumb', title: 'Watch it as users do',
        style: item.width ? `aspect-ratio:${item.width}/${item.height}` : '', onclick: () => openViewer(viewed(item), { base: BASE }) },
      thumbOf(item), item.kind === 'video' && el('span', { class: 'showcase-kind' }, icon('video'))),
      name,
      el('select', { class: 'filter', 'aria-label': 'Section', onchange: (e) => { item.section = e.target.value; save(); } },
        el('option', { value: '' }, 'No section (All only)'),
        data.sections.map((n) => el('option', { value: n, selected: n === item.section }, n))),
      el('label', { class: 'showcase-check', title: item.prompt ? 'Users see the prompt when they open it' : 'It has no prompt' },
        el('input', { type: 'checkbox', checked: item.show_prompt !== false, disabled: !item.prompt,
          onchange: (e) => { item.show_prompt = e.target.checked; save(); } }), 'Show the prompt'),
      el('div', { class: 'showcase-row' },
        el('button', { class: 'btn small', title: 'Show it earlier', disabled: at === 0, onclick: () => save(undefined, move(data.items, at, -1)) }, '←'),
        el('button', { class: 'btn small', title: 'Show it later', disabled: at === data.items.length - 1, onclick: () => save(undefined, move(data.items, at, 1)) }, '→'),
        el('span', { class: 'push' }),
        el('button', { class: 'btn small danger', onclick: () => {
          if (confirm(`Take "${item.name}" off the Home page?`)) api(`${BASE}/${item.key}`, { method: 'DELETE' }).then(ctx.draw).catch((e) => alert(e.message));
        } }, 'Remove')));
  };

  return [
    el('p', { class: 'muted', style: 'margin:0 0 14px' }, 'Every user sees this work on their Home page, under "Made on Scene.ai". '
      + 'The file is copied when you add it, so it stays even if its owner deletes it. The owner\'s name is never shown.'),
    sections,
    el('div', { class: 'toolbar', style: 'margin-top:16px' },
      segmented([{ id: '', label: `All · ${data.items.length}` }, ...data.sections.map((n) => ({ id: n, label: n }))], s.section, (v) => { s.section = v; ctx.draw(); }),
      el('span', { class: 'muted small push' }, `${data.items.length} of ${data.limit}`),
      el('button', { class: 'btn primary small', disabled: data.items.length >= data.limit, onclick: () => pickDialog(data, s.section, ctx.draw) }, 'Add from library')),
    shown.length ? el('div', { class: 'showcase-grid' }, shown.map(card))
      : el('div', { class: 'empty' }, data.items.length ? 'Nothing in this section yet.' : 'Nothing on the Home page yet: users see their own latest work there. Add the best from the library.'),
  ];
}

// Pick from every user's library: search it, choose the section, and add as many as wanted; each is copied at once.
function pickDialog(data, section, after) {
  const state = { kind: 'video', q: '', section, added: new Set(data.items.map((i) => i.from)) };
  const kinds = el('div');
  const grid = el('div', { class: 'showcase-pick' });
  const where = el('select', { class: 'filter', 'aria-label': 'Section', onchange: (e) => { state.section = e.target.value; } },
    el('option', { value: '' }, 'No section (All only)'),
    data.sections.map((n) => el('option', { value: n, selected: n === section }, n)));
  let asked = 0;
  async function draw() {
    kinds.replaceChildren(segmented([{ id: 'video', label: 'Videos' }, { id: 'image', label: 'Images' }], state.kind, (k) => { state.kind = k; draw(); }));
    const request = ++asked;
    const found = await api('/api/admin/library?' + new URLSearchParams({ kind: state.kind, q: state.q }));
    if (request !== asked) return;
    grid.replaceChildren(...(found.items.length ? found.items.map((item) => {
      const on = state.added.has(item.id);
      const add = el('button', { class: 'btn small' + (on ? '' : ' primary'), disabled: on, onclick: async () => {
        add.disabled = true;
        try {
          await api(BASE, { method: 'POST', json: { item_id: item.id, section: state.section } });
          state.added.add(item.id);
          add.textContent = 'On the Home page';
          add.classList.remove('primary');
          changed = true;
        } catch (e) { add.disabled = false; alert(e.message); }
      } }, on ? 'On the Home page' : 'Add');
      return el('div', { class: 'showcase-pick-item' },
        el('button', { type: 'button', class: 'showcase-thumb', title: 'Watch it', onclick: () => openViewer(item, { base: '/api/admin/library', owner: true }) },
          still(`/api/admin/library/${item.id}/file`, item.kind, item.name)),
        el('b', { title: item.name }, item.name),
        el('span', { class: 'muted small' }, item.user_name),
        add);
    }) : [el('div', { class: 'empty' }, 'Nothing matches.')]));
  }
  let changed = false;
  const dialog = el('dialog', { class: 'showcase-dialog' },
    el('h2', {}, 'Add to the Home page'),
    el('div', { class: 'toolbar' }, kinds, searchBox('Search name, prompt or user', '', (q) => { state.q = q; draw(); }), el('span', { class: 'push' }), el('span', { class: 'muted small' }, 'Into'), where),
    grid,
    el('div', { class: 'dialog-buttons' }, el('button', { class: 'btn', onclick: () => dialog.close() }, 'Done')));
  dialog.addEventListener('close', () => { dialog.remove(); if (changed) after(); });
  document.body.append(dialog);
  dialog.showModal();
  draw().catch((e) => grid.replaceChildren(el('p', { class: 'error' }, e.message)));
}
