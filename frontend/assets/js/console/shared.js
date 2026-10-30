// Helpers shared by the admin console sections.

import { el } from '../dom.js';
import { Spring, project, rubberband, tracker } from '../spring.js';

export const STATUS = { queued: 'Waiting', running: 'Running', done: 'Done', failed: 'Failed', cancelled: 'Cancelled' };

export const number = (value) => Number(value || 0).toLocaleString();
export const bytes = (value) => {
  if (value >= 1e9) return (value / 1e9).toFixed(1) + ' GB';
  if (value >= 1e6) return Math.round(value / 1e6) + ' MB';
  return Math.round((value || 0) / 1e3) + ' KB';
};
export const span = (seconds) => {
  if (seconds == null) return '';
  if (seconds < 90) return Math.round(seconds) + ' s';
  if (seconds < 5400) return (seconds / 60).toFixed(1).replace(/\.0$/, '') + ' min';
  return (seconds / 3600).toFixed(1) + ' h';
};
export const ago = (timestamp) => {
  if (!timestamp) return 'never';
  const seconds = Date.now() / 1000 - timestamp;
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return Math.round(seconds / 60) + ' min ago';
  if (seconds < 86400) return Math.round(seconds / 3600) + ' h ago';
  if (seconds < 86400 * 30) return Math.round(seconds / 86400) + ' d ago';
  return new Date(timestamp * 1000).toLocaleDateString([], { dateStyle: 'medium' });
};
export const stamp = (timestamp) => new Date(timestamp * 1000).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });

export const person = (name, email) => el('div', {}, name, el('div', { class: 'muted small' }, email));
export const pill = (status) => el('span', { class: 'pill ' + status }, STATUS[status] || status);
export const tile = (label, value, sub) => el('div', { class: 'tile' },
  el('div', { class: 'tile-label' }, label), el('div', { class: 'tile-value' }, String(value)), sub && el('div', { class: 'muted small' }, sub));

// rows: arrays of cells. `onRow(index)` makes rows clickable.
export function table(head, rows, { onRow, empty = 'Nothing here yet.' } = {}) {
  return el('div', { class: 'table-wrap' }, el('table', {},
    el('tr', {}, head.map((h) => el('th', {}, h))),
    rows.length
      ? rows.map((cells, i) => el('tr', { class: onRow ? 'clickable' : '', tabindex: onRow ? 0 : null,
        onclick: onRow ? () => onRow(i) : null, onkeydown: onRow ? (e) => { if (e.key === 'Enter') onRow(i); } : null },
      cells.map((c) => el('td', {}, c))))
      : el('tr', {}, el('td', { colspan: head.length, class: 'muted' }, empty))));
}

// A search box that calls back a moment after typing stops.
export function searchBox(placeholder, value, onChange) {
  let timer;
  return el('input', { type: 'text', class: 'search', placeholder, value,
    oninput: (e) => { clearTimeout(timer); timer = setTimeout(() => onChange(e.target.value), 250); } });
}

export const exportLink = (name) => el('a', { class: 'btn small', href: `/api/admin/export/${name}.csv`, download: '' }, 'Export CSV');

// A panel that slides in from the right for the details of one user or job. It rides on a spring: its head can be
// dragged and flicked to the right to put it away, it leaves the way it came, and the shade behind it follows it.
export function drawer(title, content) {
  let closing = false;
  const close = (velocity) => {
    if (closing) return;
    closing = true;
    document.removeEventListener('keydown', onKey);
    backdrop.style.pointerEvents = 'none';
    spring.to(width(), { response: 0.3, velocity: typeof velocity === 'number' ? velocity : undefined, done: () => backdrop.remove() });
  };
  const onKey = (e) => { if (e.key === 'Escape') close(); };
  const body = el('div', { class: 'drawer-body' }, content);
  const head = el('div', { class: 'drawer-head' }, el('h2', {}, title), el('button', { class: 'btn small', onclick: () => close() }, 'Close'));
  const panel = el('aside', { class: 'drawer', role: 'dialog', 'aria-label': title }, head, body);
  const backdrop = el('div', { class: 'drawer-backdrop', onclick: (e) => { if (e.target === backdrop) close(); } }, panel);
  document.querySelectorAll('.drawer-backdrop').forEach((d) => d.remove());
  document.body.append(backdrop);
  document.addEventListener('keydown', onKey);
  const width = () => panel.offsetWidth || 580;
  const spring = new Spring(width(), (x) => {
    panel.style.transform = x ? `translateX(${x}px)` : '';
    backdrop.style.setProperty('--shown', Math.max(0, Math.min(1, 1 - x / width())));
  });
  spring.to(0, { response: 0.35 });

  // The head is the handle. Past the left edge it gives a little; let go far enough or fast enough and it goes away.
  head.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || e.target.closest('button, a, input, select, textarea') || closing) return;
    head.setPointerCapture(e.pointerId);
    spring.stop();
    const from = { pointer: e.clientX, x: spring.x };
    const speed = tracker();
    speed.add(e.clientX);
    const onMove = (ev) => {
      speed.add(ev.clientX);
      const x = from.x + ev.clientX - from.pointer;
      spring.set(x < 0 ? -rubberband(-x, width()) : x);
    };
    const end = () => {
      head.removeEventListener('pointermove', onMove);
      head.removeEventListener('pointerup', end);
      head.removeEventListener('pointercancel', end);
      const velocity = speed.velocity().x;
      if (spring.x + project(velocity) > width() / 3) close(velocity);
      else spring.to(0, { response: 0.3, damping: Math.abs(velocity) > 400 ? 0.8 : 1, velocity });
    };
    head.addEventListener('pointermove', onMove);
    head.addEventListener('pointerup', end);
    head.addEventListener('pointercancel', end);
  });
  return { close: () => close(), replace: (...nodes) => body.replaceChildren(...nodes.flat().filter(Boolean)) };
}

export const section = (title, ...content) => el('div', { class: 'drawer-section' }, el('h3', {}, title), ...content);
export const facts = (pairs) => el('dl', { class: 'facts' }, pairs.filter((p) => p && p[1] != null && p[1] !== '' && p[1] !== false).flatMap(([k, v]) => [el('dt', {}, k), el('dd', {}, v)]));
