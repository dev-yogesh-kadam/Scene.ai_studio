// Cards for finished images and videos, and the viewer with its details panel.

import { api } from '../api.js';
import { ask, still, el, icon, duration, when } from '../dom.js';
import { store } from '../store.js';
import { KIT, addToKitDialog } from './kit.js';
import { go } from '../nav.js';
import { Spring } from '../spring.js';
import { popover } from './agent.js';

const title = (text) => String(text).replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
const fileSize = (bytes) => (bytes >= 1e9 ? (bytes / 1e9).toFixed(1) + ' GB' : bytes >= 1e6 ? (bytes / 1e6).toFixed(1) + ' MB' : Math.round((bytes || 0) / 1e3) + ' KB');

// The prompt a generation was made with. Older items don't store it separately, so fall back to the longest text setting.
export function promptOf(item) {
  const settings = item.settings || {};
  if (settings.prompt != null) return settings.prompt;
  return Object.values(settings.values || {}).filter((v) => typeof v === 'string').sort((a, b) => b.length - a.length)[0] || '';
}

// Open Create with a result's settings and its own seed: the same picture again, with what is then changed (a Draft made
// Final, a word of the prompt). Only for work made with a seed.
export const seedOf = (item) => (item.context && item.context.seed != null ? item.context.seed : null);
export function reuseSeed(item, from = null) {
  store.rerun = item;
  store.reuseSeed = seedOf(item);
  store.from = from;
  go('/create');
}

// The facts about a generation that are worth showing: [label, value] pairs, empty ones left out.
export function detailsOf(item, { owner } = {}) {
  const s = item.settings || {};
  const c = item.context || {};
  const made = new Date(item.created * 1000);
  const refs = Object.values(s.refs || {}).map((r) => r.name || r.comfy_name).filter(Boolean);
  return [
    owner && ['Made by', `${item.user_name} · ${item.user_email}`],
    ['Type', title(item.kind)],
    ['Workflow', s.workflow_title || title(item.workflow.split('/')[1])],
    ...Object.entries(s.options || {}).map(([k, v]) => [title(k), title(v)]),
    ['Resolution', c.width ? `${c.width} × ${c.height}` + (c.resolution ? ` (${c.resolution}p ${c.orientation || ''})` : '') : c.resolution ? c.resolution + 'p' : null],
    ['Length', c.duration ? (c.clips > 1 ? `${c.clips} clips of ${c.duration} s` : `${c.duration} s`) : null],
    ['Seed', c.seed != null ? String(c.seed) : null],
    ...(s.details || []).map(([k, v]) => [k, typeof v === 'boolean' ? (v ? 'On' : 'Off') : String(v)]),
    ['References', refs.join(', ')],
    ['Project', item.project_name],
    ['Date', made.toLocaleDateString([], { dateStyle: 'long' })],
    ['Time', made.toLocaleTimeString([], { timeStyle: 'short' })],
    ['Render time', item.seconds ? duration(item.seconds) : null],
    ['Credits', item.cost ? String(item.cost) : null],
    ['File', `${item.filename} · ${fileSize(item.size)}`],
    ['Generation ID', String(item.id)],
    ['Job ID', item.job_id],
  ].filter((row) => row && row[1] != null && row[1] !== '');
}

// The viewer grows out of the picture that was clicked and goes back into it when it closes, so it is always clear
// where it came from. The last press anywhere is remembered to find that picture.
let pressed = null;
document.addEventListener('pointerdown', (e) => { pressed = e.target; }, true);

// The picture under the last press: an image or a video shown in what was pressed.
function pressedPicture() {
  const holder = pressed && pressed.isConnected && pressed.closest('button, a, [role="button"], .frame, .media, .made, .thumb');
  const pic = holder && holder.querySelector('img, video');
  if (!pic || !pic.getBoundingClientRect().width) return null;
  const size = pic.tagName === 'IMG' ? [pic.naturalWidth, pic.naturalHeight] : [pic.videoWidth, pic.videoHeight];
  return size[0] && size[1] ? { pic, w: size[0], h: size[1] } : null;
}

// A still of the picture to fly: the image itself, or the frame a video is showing.
function snapshot(pic, w, h) {
  if (pic.tagName === 'IMG') return el('img', { src: pic.currentSrc || pic.src, alt: '' });
  try {
    const canvas = el('canvas', { width: w, height: h });
    canvas.getContext('2d').drawImage(pic, 0, 0, w, h);
    return canvas;
  } catch { return null; }
}

// Where the picture will sit in the viewer: as large as fits, never larger than it is, in the middle.
function landing(area, w, h) {
  const box = area.getBoundingClientRect();
  const pad = parseFloat(getComputedStyle(area).paddingLeft) || 0;
  const scale = Math.min(1, (box.width - pad * 2) / w, (Math.min(box.height, innerHeight) - pad * 2) / h);
  return { x: box.left + (box.width - w * scale) / 2, y: box.top + (Math.min(box.height, innerHeight) - h * scale) / 2, w: w * scale, h: h * scale };
}

// The still flies between the thumbnail and the viewer on one spring, 0 at the thumbnail and 1 in the viewer. Closing
// while it is still opening turns it round from where it is.
function flyFrom(dialog, area, source) {
  const flyer = snapshot(source.pic, source.w, source.h);
  if (!flyer) return null;
  flyer.classList.add('viewer-flyer');
  dialog.append(flyer);
  dialog.classList.add('flying');
  let from = source.pic.getBoundingClientRect();
  const to = landing(area, source.w, source.h);
  const put = (p) => {
    const w = from.width + (to.w - from.width) * p;
    const h = from.height + (to.h - from.height) * p;
    flyer.style.transform = `translate(${from.left + (to.x - from.left) * p}px, ${from.top + (to.y - from.top) * p}px)`;
    flyer.style.width = w + 'px';
    flyer.style.height = h + 'px';
    dialog.style.setProperty('--open', Math.max(0, Math.min(1, p)));
  };
  const spring = new Spring(0, put, 0.001);
  spring.to(1, { response: 0.42, done: () => { dialog.classList.remove('flying'); flyer.remove(); } });
  return {
    back(done) {
      if (!source.pic.isConnected) return false;
      from = source.pic.getBoundingClientRect();   // it may have moved while the viewer was open
      if (!flyer.isConnected) { dialog.append(flyer); put(spring.x); }
      dialog.classList.add('flying', 'leaving');
      spring.to(0, { response: 0.36, done });
      return true;
    },
  };
}

/// base: where the file is served from. owner: show who made it (admin). actions: extra buttons, for the item opened.
// takes: the takes of the stack the item is on, {items: oldest first, chosen: the id of the one in use, choose(item)}.
// A strip under the picture shows them all, the one in use marked; any can be looked at, and put in use from here.
export function openViewer(item, { base = '/api/library', owner = false, actions = [], takes = null } = {}) {
  const source = pressedPicture();
  const mediaBox = el('div', { class: 'viewer-media' + (takes ? ' with-takes' : '') });
  const heading = el('h2');
  const scroll = el('div', { class: 'viewer-scroll' });
  const buttons = el('div', { class: 'viewer-actions' });
  const glowBox = el('div', { class: 'viewer-glow', 'aria-hidden': 'true' });
  const strip = takes && el('div', { class: 'viewer-takes', role: 'listbox', 'aria-label': 'Takes' });
  let download = null;
  let current = item;

  // What belongs to the item shown: its picture, its name, its prompt and details, and its buttons.
  function show(shown) {
    current = shown;
    const url = `${base}/${shown.id}/file`;
    const media = shown.kind === 'video' ? el('video', { src: url, controls: true, autoplay: true, loop: true })
      : shown.kind === 'audio' ? el('audio', { src: url, controls: true, autoplay: true })
        : shown.kind === 'text' ? el('pre', { class: 'viewer-text' }, 'Loading…')
          : el('img', { src: url, alt: shown.name });
    // A text is shown as it is: its first 200,000 characters
    if (shown.kind === 'text') fetch(url).then((r) => (r.ok ? r.text() : Promise.reject(new Error(r.statusText))))
      .then((text) => { media.textContent = text.length > 200000 ? text.slice(0, 200000) + '\n…' : text; })
      .catch(() => { media.textContent = 'This text could not be loaded.'; });
    const promptText = promptOf(shown);
    const copy = el('button', { class: 'btn small quiet', onclick: async () => {
      try { await navigator.clipboard.writeText(promptText); copy.textContent = 'Copied'; } catch (e) { copy.textContent = 'Copy failed'; }
      setTimeout(() => { copy.textContent = 'Copy'; }, 1500);
    } }, 'Copy');
    download = el('a', { class: 'btn primary', href: url + '?download=true', download: shown.filename, title: 'Download (D)' }, 'Download');
    // The user's thumbs on their own result: the agent reuses what they liked and never what they turned down.
    const thumbs = base === '/api/library' && !owner && shown.workflow && el('span', { class: 'rate viewer-rate' });
    const drawThumbs = () => thumbs && thumbs.replaceChildren(...[[1, 'thumbup', 'Good: the agent will reuse it'], [-1, 'thumbdown', 'Not good: the agent will not use it']].map(([value, glyph, tip]) =>
      el('button', { type: 'button', class: 'icon-btn' + (shown.rating === value ? ' on' + (value < 0 ? ' bad' : '') : ''), title: tip, 'aria-label': tip,
        'aria-pressed': String(shown.rating === value), onclick: async () => {
          const before = shown.rating || 0;
          shown.rating = before === value ? 0 : value;
          drawThumbs();
          try { await api('/api/library/' + shown.id, { method: 'PUT', json: { rating: shown.rating } }); } catch (e) { shown.rating = before; drawThumbs(); alert(e.message); }
        } }, icon(glyph))));
    drawThumbs();
    // Cinema: the studio goes dark and the picture's own colours glow around it, like light off a screen.
    const glow = shown.kind === 'audio' ? '' : shown.kind === 'video' ? `${base}/${shown.id}/poster` : url;
    glowBox.style.setProperty('--spill-image', glow ? `url("${glow}")` : 'none');
    mediaBox.replaceChildren(media, ...(strip ? [strip] : []));
    heading.textContent = shown.name;
    scroll.replaceChildren(...[
      promptText && el('div', { class: 'viewer-section' }, el('div', { class: 'label-row' }, el('h3', {}, 'Prompt'), copy), el('p', { class: 'prose' }, promptText)),
      el('div', { class: 'viewer-section' }, el('h3', {}, 'Details'),
        el('dl', { class: 'facts' }, detailsOf(shown, { owner }).flatMap(([k, v]) => [el('dt', {}, k), el('dd', {}, v)])))].filter(Boolean));
    // A take that is not the one in use can be put in use from here: it goes on top of its stack.
    const use = takes && shown.id !== takes.chosen && el('button', { class: 'btn', title: 'Put this take on top and go on with it',
      onclick: () => { takes.chosen = shown.id; takes.choose(shown); show(shown); } }, 'Use this take');
    buttons.replaceChildren(...[download, thumbs, use,
      ...(shown === item ? actions : []).map((a) => el('button', { class: 'btn' + (a.danger ? ' danger' : ''), onclick: () => a.run(dialog) }, a.label))].filter(Boolean));
    drawStrip();
  }

  // The takes, oldest first: the one in use says so, the one shown is ringed.
  function drawStrip() {
    if (!strip) return;
    strip.replaceChildren(...takes.items.map((t, i) => el('button', { type: 'button', role: 'option', 'aria-selected': String(t.id === current.id),
      class: 'viewer-take' + (t.id === current.id ? ' shown' : '') + (t.id === takes.chosen ? ' chosen' : ''),
      title: t.id === takes.chosen ? `Take ${i + 1}: in use` : `Take ${i + 1}`, onclick: () => { if (t.id !== current.id) show(t); } },
      el('span', { class: 'viewer-take-pic' }, still(`${base}/${t.id}/file`, t.kind, t.name)),
      el('span', { class: 'viewer-take-label' }, `Take ${i + 1}`, t.id === takes.chosen && el('b', {}, ' · In use')))));
  }

  const dialog = el('dialog', { class: 'viewer' },
    glowBox,
    el('div', { class: 'viewer-grid' },
      mediaBox,
      el('aside', { class: 'viewer-panel' },
        el('div', { class: 'viewer-title' }, heading, el('button', { class: 'icon-btn', title: 'Close', 'aria-label': 'Close', onclick: () => leave() }, '×')),
        scroll,
        buttons)));
  show(item);
  dialog.addEventListener('close', () => dialog.remove());
  dialog.addEventListener('keydown', (e) => {
    if (e.repeat || e.metaKey || e.ctrlKey || e.altKey || e.target.closest('input, textarea, select')) return;
    if (e.key.toLowerCase() === 'd') { e.preventDefault(); download.click(); return; }
    // ← and → go through the takes
    if (takes && (e.key === 'ArrowLeft' || e.key === 'ArrowRight') && !e.target.closest('video, audio')) {
      const next = takes.items[takes.items.findIndex((t) => t.id === current.id) + (e.key === 'ArrowRight' ? 1 : -1)];
      if (next) { e.preventDefault(); show(next); }
    }
  });
  // A click in the dark around the picture closes it, as a click outside a smaller dialog would.
  dialog.addEventListener('click', (e) => { if (e.target === dialog || e.target.classList.contains('viewer-media')) leave(); });
  // Esc, the close button and a click outside send the picture back to where it came from before the viewer closes
  // (when another take is shown, it just closes: the picture it came from is not that one).
  let trip = null;
  let leaving = false;
  const leave = () => {
    if (leaving) return;
    leaving = true;
    if (current !== item || !trip || !trip.back(() => dialog.close())) dialog.close();
  };
  dialog.addEventListener('cancel', (e) => { e.preventDefault(); leave(); });
  document.body.append(dialog);
  dialog.showModal();
  // The viewer itself takes the focus, not its close button: the Enter that opened it must not close it again.
  dialog.tabIndex = -1;
  dialog.focus();
  if (source && (item.kind === 'image' || item.kind === 'video')) trip = flyFrom(dialog, mediaBox, source);
  return dialog;
}

// Open Create with this item as the first frame: an image as it is, a video's last frame.
async function useAsFirstFrame(item, button) {
  if (button) button.disabled = true;
  try {
    const ref = await api(`/api/library/${item.id}/reference`, { method: 'POST' });
    store.prefill = { slot: 'first_frame', ref, parent: item.id };
    go('/create');
    return true;
  } catch (e) { alert(e.message); if (button) button.disabled = false; return false; }
}

// `manage` adds the library-only actions: move to a project, save as asset, delete.
export function mediaCard(item, { manage, projects = [], onChanged } = {}) {
  const fileUrl = `/api/library/${item.id}/file`;
  const thumb = still(fileUrl, item.kind, item.name);
  const sound = item.kind === 'audio';   // a sound can't be the first frame of a video
  const rerun = () => { store.rerun = item; go('/create'); };
  const next = item.kind === 'video' ? 'Continue' : 'Use as first frame';
  const remove = async () => {
    if (!await ask({ title: `Delete "${item.name}"?`, danger: true, confirm: 'Delete', message: "It is deleted from your library for good. This can't be undone." })) return;
    try { await api('/api/library/' + item.id, { method: 'DELETE' }); onChanged(); } catch (e) { alert(e.message); }
  };
  const move = async (e) => {
    try {
      await api('/api/library/' + item.id, { method: 'PUT', json: { project_id: Number(e.target.value) || null } });
      onChanged();
    } catch (err) { alert(err.message); }
  };
  const edited = /^(edit|upload)\//.test(item.workflow);   // an edit or an upload: there is no form to re-run
  const view = () => openViewer(item, { actions: [
    !edited && { label: 'Re-run', run: (dialog) => { dialog.close(); rerun(); } },
    !edited && seedOf(item) != null && { label: 'Reuse seed', run: (dialog) => { dialog.close(); reuseSeed(item); } },
    !sound && { label: next, run: async (dialog) => { if (await useAsFirstFrame(item)) dialog.close(); } },
  ].filter(Boolean) });
  // The card is the picture and its name. Its actions wait on the picture until the pointer is on it (always shown on
  // a touch screen): the next step as one clear button, Download, and the rest in a "…" menu.
  const project = projects.find((p) => p.id === item.project_id);
  const moveMenu = (anchor) => popover(anchor, [el('div', { class: 'pop-title' }, 'Move to project'),
    ...[{ id: 0, name: 'No project' }, ...projects].map((p) => el('button', { type: 'button', class: 'pop-item', role: 'menuitemradio',
      'aria-checked': String((item.project_id || 0) === p.id),
      onclick: (e) => { e.currentTarget.closest('.pop').close(); move({ target: { value: p.id } }); } },
      el('span', {}, el('b', {}, p.parent_name ? `${p.parent_name} › ${p.name}` : p.name)), (item.project_id || 0) === p.id && icon('check')))]);
  const more = el('button', { type: 'button', class: 'card-tool', title: 'More', 'aria-label': `More for ${item.name}`, 'aria-haspopup': 'menu',
    onclick: (e) => {
      e.stopPropagation();
      const close = () => box.close();
      const row = (glyph, label, run, cls = '') => el('button', { type: 'button', class: 'pop-item ' + cls, role: 'menuitem', onclick: () => { close(); run(); } }, icon(glyph), label);
      const box = popover(more, [
        !edited && row('retry', 'Re-run with the same settings', rerun),
        manage && row('folder', project ? `Move from ${project.name}…` : 'Move to a project…', () => moveMenu(more)),
        manage && item.kind !== 'text' && item.project_id && row('memory', `Add to ${KIT}`, () => addToKitDialog({ project: item.project_id || 0, item })),
        manage && el('div', { class: 'menu-sep' }),
        manage && row('trash', 'Delete', remove, 'danger'),
      ].filter(Boolean), 'card-menu');
    } }, icon('more'));
  const tools = el('div', { class: 'card-tools' },
    el('a', { class: 'card-tool', href: fileUrl + '?download=true', download: item.filename, title: 'Download', 'aria-label': `Download ${item.name}`,
      onclick: (e) => e.stopPropagation() }, icon('download')),
    (!edited || manage) && more);
  const nextButton = !sound && el('button', { type: 'button', class: 'card-go', title: item.kind === 'video' ? 'Start a new video on the last frame of this one' : 'Start a video on this image',
    onclick: (e) => { e.stopPropagation(); useAsFirstFrame(item, e.currentTarget); } }, icon('forward'), next);
  return el('div', { class: 'media' },
    el('div', { class: 'thumb', onclick: view }, thumb, el('span', { class: 'kind' }, item.kind),
      item.rating ? el('span', { class: 'rated' + (item.rating < 0 ? ' bad' : ''), title: item.rating > 0 ? 'You liked it' : 'You turned it down' },
        icon(item.rating > 0 ? 'thumbup' : 'thumbdown')) : null,
      tools, nextButton),
    el('div', { class: 'meta' },
      el('div', { class: 'title', title: item.name }, item.name),
      el('div', { class: 'sub' }, [manage && project ? project.name : '', item.summary, item.seconds && 'took ' + duration(item.seconds)].filter(Boolean).join(' · ') || when(item.created))));
}
