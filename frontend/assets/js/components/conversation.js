// The pieces the agent's conversation is drawn with: replies in light markdown with small pictures of the items they
// name, rows that fold open ("Thought for 6s", "Worked 12s · Checked the result"), and the rows of the agent's work.
// Nothing the model wrote is ever put in the page as HTML: every word becomes a text node.

import { el, icon, still } from '../dom.js';

// "6s", "1m 20s".
export const span = (seconds) => {
  const s = Math.max(0, Math.round(seconds || 0));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`;
};
// "0:04", the place of a frame in a clip.
export const clock = (seconds) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;

const ITEM_URL = { item: (id) => `/api/library/${id}/file`, asset: (id) => `/api/kit/${id}/file` };

// An item or a saved asset named in a message: its picture and its name. onPick(table, id) when it is clicked.
export function chip(table, id, known, onPick) {
  return el('button', { type: 'button', class: 'md-chip', title: known.name, onclick: () => onPick(table, id) },
    el('span', { class: 'md-chip-thumb' }, still(ITEM_URL[table](id), known.kind, known.name)), el('span', { class: 'md-chip-name' }, known.name));
}

// A file the reply hands over ([[show:item:12]] on a line of its own): the video, picture or sound itself to play there,
// its name, and Download, Copy link (the studio's own link, /api/m/<id>: it opens only for someone signed in who may
// see it) and Open (where it is in the studio).
export function mediaCard(table, id, known, onPick) {
  const url = ITEM_URL[table](id);
  const view = known.kind === 'video'
    ? el('video', { src: url, controls: true, preload: 'metadata', playsinline: true, poster: table === 'item' ? `/api/library/${id}/poster` : null })
    : known.kind === 'image' ? el('img', { src: url, alt: known.name, loading: 'lazy' })
      : known.kind === 'audio' ? soundPlayer(url, known.name) : null;
  const copy = el('button', { type: 'button', class: 'md-media-act', title: 'Copy link' }, icon('copy'), 'Copy link');
  copy.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(new URL(known.link || url, location.origin).href);
      copy.lastChild.textContent = 'Copied';
    } catch { copy.lastChild.textContent = 'Could not copy'; }
    setTimeout(() => { copy.lastChild.textContent = 'Copy link'; }, 1600);
  });
  const save = table === 'item' ? `/api/library/${id}/file?download=1` : url;
  return el('figure', { class: `md-media md-media-${known.kind}`, 'data-key': `${table}:${id}` },
    view && el('div', { class: 'md-media-view' }, view),
    el('figcaption', {},
      el('span', { class: 'md-media-name', title: known.name }, known.name),
      el('a', { class: 'md-media-act', href: save, download: table === 'item' ? null : known.name, title: 'Download' }, icon('download'), 'Download'),
      copy,
      el('button', { type: 'button', class: 'md-media-act', title: 'Open in the studio', onclick: () => onPick(table, id) }, icon('expand'), 'Open')));
}

const SHOW_LINE = /^\s*\[\[show:(item|asset):(\d+)\]\]\s*$/;

// One line of a reply: **bold**, *italic*, `code` and [[item:12]] / [[asset:3]] ([[show:…]] inside a line is a chip too).
function inline(text, chips, onPick) {
  const parts = [];
  const pattern = /\[\[(?:show:)?(item|asset):(\d+)\]\]|\*\*([^*]+)\*\*|`([^`]+)`|(?<![\w*])\*([^*\s][^*]*?)\*(?![\w*])/g;
  let last = 0;
  let found;
  while ((found = pattern.exec(text))) {
    if (found.index > last) parts.push(document.createTextNode(text.slice(last, found.index)));
    if (found[1]) {
      const known = chips[`${found[1]}:${found[2]}`];
      if (known) parts.push(chip(found[1], Number(found[2]), known, onPick));
    } else if (found[3]) parts.push(el('b', {}, found[3]));
    else if (found[4]) parts.push(el('code', {}, found[4]));
    else if (found[5]) parts.push(el('i', {}, found[5]));
    last = pattern.lastIndex;
  }
  if (last < text.length) parts.push(document.createTextNode(text.slice(last)));
  return parts;
}

const LIST = /^\s*([-*•]|\d+[.)])\s+/;
const FENCE = /```csv[ \t]*\n([\s\S]*?)\n```/g;
const LIBRARY_LINK = /^\/api\/(library|assets)\/(\d+)\/file$/;

// One row of CSV: commas split cells, a cell in double quotes may hold commas ("" is a quote mark).
function csvRow(line) {
  const cells = [];
  let cell = '';
  let quoted = false;
  for (let i = 0; i < line.length; i += 1) {
    const c = line[i];
    if (quoted && c === '"' && line[i + 1] === '"') { cell += '"'; i += 1; }
    else if (c === '"') quoted = !quoted;
    else if (c === ',' && !quoted) { cells.push(cell.trim()); cell = ''; }
    else cell += c;
  }
  cells.push(cell.trim());
  return cells;
}

// A cell of a table: a link to one of the user's library items (or kit entries) shows its picture — a video its
// poster, found when the file itself is not a picture; anything else is text. Only the studio's own links are shown.
function tableCell(text) {
  const found = LIBRARY_LINK.exec(text);
  if (!found) return el('td', {}, text);
  const img = el('img', { src: text, alt: '', loading: 'lazy' });
  img.addEventListener('error', () => {
    if (found[1] === 'library' && !img.dataset.poster) { img.dataset.poster = '1'; img.src = `/api/library/${found[2]}/poster`; }
    else img.replaceWith(el('a', { href: text, target: '_blank', rel: 'noopener' }, 'open'));
  });
  return el('td', { class: 'md-cell-media' }, el('a', { href: text, target: '_blank', rel: 'noopener', title: text }, img));
}

// A table in a box of its own that scrolls inside the reply, its header staying in view, with Copy (the CSV, for a
// spreadsheet) and Download (a .csv file) at its top right.
function table(csv) {
  const [head, ...rows] = csv.split('\n').filter((line) => line.trim()).map(csvRow);
  const done = (button, text) => { const was = button.title; button.title = text; button.classList.add('done'); setTimeout(() => { button.title = was; button.classList.remove('done'); }, 1500); };
  const tools = el('div', { class: 'md-table-tools' },
    el('button', { type: 'button', class: 'icon-btn small', title: 'Copy the table', 'aria-label': 'Copy the table',
      onclick: (e) => { const b = e.currentTarget; navigator.clipboard.writeText(csv.trim()).then(() => done(b, 'Copied')).catch(() => {}); } }, icon('copy')),
    el('button', { type: 'button', class: 'icon-btn small', title: 'Download as CSV', 'aria-label': 'Download the table as CSV',
      onclick: () => {
        const url = URL.createObjectURL(new Blob([csv.trim() + '\n'], { type: 'text/csv' }));
        el('a', { href: url, download: 'table.csv' }).click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } }, icon('download')));
  return el('div', { class: 'md-table-box' }, tools, el('div', { class: 'md-table' }, el('table', {},
    el('thead', {}, el('tr', {}, (head || []).map((h) => el('th', {}, h)))),
    el('tbody', {}, rows.map((cells) => el('tr', {}, cells.map(tableCell)))))));
}

// A sound as a player: a round play button, its waveform (drawn from the file the first time it is shown) that also
// shows how far it has played and can be clicked to jump, and its length. One sound plays at a time.
const WAVE_BARS = 64;
const waves = new Map();   // url -> the bar heights, once worked out
export function soundPlayer(url, name = '') {
  const audio = el('audio', { src: url, preload: 'metadata' });
  const play = el('button', { type: 'button', class: 'wave-play', 'aria-label': 'Play ' + name, title: 'Play' }, icon('play'));
  const bars = el('div', { class: 'wave-bars', role: 'slider', 'aria-label': 'Position', 'aria-valuemin': '0', 'aria-valuemax': '100', tabindex: '0' });
  const time = el('span', { class: 'wave-time' }, '0:00');
  const node = el('div', { class: 'wave' }, play, bars, time, audio);
  const draw = (heights) => bars.replaceChildren(...heights.map((h) => el('i', { style: `height:${Math.max(8, Math.round(h * 100))}%` })));
  draw(waves.get(url) || Array.from({ length: WAVE_BARS }, (_, i) => 0.25 + 0.15 * Math.abs(Math.sin(i * 0.7))));
  const progress = () => {
    const share = audio.duration ? audio.currentTime / audio.duration : 0;
    const lit = Math.round(share * WAVE_BARS);
    [...bars.children].forEach((bar, i) => bar.classList.toggle('on', i < lit));
    bars.setAttribute('aria-valuenow', String(Math.round(share * 100)));
    time.textContent = clock(audio.paused && !audio.currentTime ? audio.duration || 0 : audio.currentTime);
  };
  audio.addEventListener('loadedmetadata', progress);
  audio.addEventListener('timeupdate', progress);
  audio.addEventListener('play', () => { document.querySelectorAll('.wave audio').forEach((a) => { if (a !== audio) a.pause(); }); play.replaceChildren(icon('pause')); play.title = 'Pause'; });
  audio.addEventListener('pause', () => { play.replaceChildren(icon('play')); play.title = 'Play'; });
  audio.addEventListener('ended', () => { audio.currentTime = 0; progress(); });
  play.addEventListener('click', () => (audio.paused ? audio.play().catch(() => {}) : audio.pause()));
  const seek = (share) => { if (audio.duration) { audio.currentTime = Math.max(0, Math.min(1, share)) * audio.duration; progress(); } };
  bars.addEventListener('click', (e) => { const r = bars.getBoundingClientRect(); seek((e.clientX - r.left) / r.width); });
  bars.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { e.preventDefault(); audio.currentTime = Math.max(0, audio.currentTime + (e.key === 'ArrowRight' ? 5 : -5)); progress(); }
  });
  // The real waveform: the file read once when the player is first seen, its loudness in WAVE_BARS slices.
  if (!waves.has(url) && 'IntersectionObserver' in window) {
    const seen = new IntersectionObserver(async (entries) => {
      if (!entries.some((e) => e.isIntersecting)) return;
      seen.disconnect();
      try {
        const data = await (await fetch(url)).arrayBuffer();
        if (data.byteLength > 40e6) return;   // a very long sound keeps the drawn shape
        const Context = window.AudioContext || window.webkitAudioContext;
        const context = new Context();
        const decoded = await context.decodeAudioData(data);
        context.close();
        const samples = decoded.getChannelData(0);
        const step = Math.floor(samples.length / WAVE_BARS) || 1;
        const peaks = Array.from({ length: WAVE_BARS }, (_, i) => {
          let sum = 0;
          for (let j = i * step; j < (i + 1) * step && j < samples.length; j += 32) sum += samples[j] * samples[j];
          return Math.sqrt(sum / (step / 32));
        });
        const top = Math.max(...peaks) || 1;
        const heights = peaks.map((p) => p / top);
        waves.set(url, heights);
        draw(heights);
        progress();
      } catch { /* the drawn shape stays */ }
    });
    seen.observe(node);
  }
  return node;
}

// A reply as paragraphs, lists and ```csv tables. chips: {"item:12": {name, kind}} for the items it may name.
export function markdown(text, chips = {}, onPick = () => {}) {
  const out = [];
  const source = String(text || '').replace(/\r/g, '');
  let at = 0;
  for (const found of source.matchAll(FENCE)) {
    out.push(...prose(source.slice(at, found.index), chips, onPick), table(found[1]));
    at = found.index + found[0].length;
  }
  return [...out, ...prose(source.slice(at), chips, onPick)];
}

function prose(text, chips, onPick) {
  const out = [];
  for (const block of text.split(/\n{2,}/)) {
    let list = null;
    let paragraph = null;
    for (const line of block.split('\n')) {
      const shown = SHOW_LINE.exec(line);
      if (shown) {
        const known = chips[`${shown[1]}:${shown[2]}`];
        if (known) { list = null; paragraph = null; out.push(mediaCard(shown[1], Number(shown[2]), known, onPick)); }
      } else if (LIST.test(line)) {
        paragraph = null;
        const ordered = /^\s*\d/.test(line);
        if (!list || list.ordered !== ordered) {
          list = { ordered, node: el(ordered ? 'ol' : 'ul') };
          out.push(list.node);
        }
        list.node.append(el('li', {}, inline(line.replace(LIST, ''), chips, onPick)));
      } else if (line.trim()) {
        list = null;
        if (!paragraph) { paragraph = el('p'); out.push(paragraph); } else paragraph.append(el('br'));
        paragraph.append(...inline(line, chips, onPick));
      }
    }
  }
  return out;
}

// A row that folds open: an icon, a title, a quieter word after it, and what it holds. `state` keeps whether it is open
// (state.open), so it stays open when the conversation is drawn again. Without a body it is a plain row. `glyphs`, in
// place of one glyph, shows a small overlapping stack of marks: one for each kind of thing the fold holds.
export function fold({ glyph, glyphs = null, title, sub = '', state = {}, body = null, className = '', onToggle = () => {} }) {
  const has = Boolean(body);
  const marks = glyphs && glyphs.length ? el('span', { class: 'fold-glyphs', 'aria-hidden': 'true' }, glyphs.map((g) => el('span', {}, icon(g))))
    : glyph && icon(glyph);
  const head = el(has ? 'button' : 'div', { class: 'fold-head', ...(has ? { type: 'button', 'aria-expanded': String(Boolean(state.open)),
    onclick: () => { state.open = !state.open; onToggle(); } } : {}) },
    marks, el('span', { class: 'fold-title' }, title), sub && el('span', { class: 'fold-sub' }, sub),
    has && el('span', { class: 'fold-caret', 'aria-hidden': 'true' }, icon(state.open ? 'down' : 'right')));
  return el('div', { class: 'fold ' + className + (state.open ? ' open' : '') }, head, has && state.open && el('div', { class: 'fold-body' }, body));
}

const WORK_ICONS = { attach: 'attachment', bulb: 'bulb', book: 'book', look: 'eye', skill: 'skill', retry: 'retry', skip: 'skip', plan: 'check',
  queue: 'queue', wait: 'clock', ready: 'film', check: 'check', warn: 'skip', status: 'wrench' };

// The marks of some work, one of each kind it did and at most three: what a closed fold shows in front of its title.
export function glyphsOf(entries) {
  const names = [];
  for (const entry of entries) {
    const name = entry.type === 'thought' ? 'bulb' : WORK_ICONS[entry.icon] || 'wrench';
    if (!names.includes(name)) names.push(name);
  }
  return names.slice(0, 3);
}

// The rows of the agent's work. A thought among them is a fold of its own.
export function workRows(entries, states, redraw) {
  return entries.map((entry, i) => (entry.type === 'thought'
    ? fold({ glyph: 'bulb', title: `Thought for ${span(entry.seconds)}`, state: (states[i] = states[i] || {}), onToggle: redraw,
      body: entry.text ? el('p', { class: 'fold-text' }, entry.text) : null, className: 'nested' })
    : el('div', { class: 'work-row' }, icon(WORK_ICONS[entry.icon] || 'wrench'), el('span', {}, entry.text))));
}
