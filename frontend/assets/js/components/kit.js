// The kit of a project: everything it is made from, by name (characters, locations, props, outfits, voices, styles and
// scripts). The agent knows each entry by its name and what it shows; an entry that is "always on" goes into every shot
// that has a slot for it (what the cast was). One panel for what the Cast box and the Shared memory tab were.

import { api } from '../api.js';
import { ago, ask, el, field, icon, openDialog, segmented } from '../dom.js';
import { addMenu } from './agent.js';
import { Spring, rubberband } from '../spring.js';

export const KIT = 'NeuralCore';   // what the feature is called wherever the user reads it
export const KIT_TYPES = [
  { id: 'character', label: 'Character' }, { id: 'location', label: 'Location' }, { id: 'prop', label: 'Prop' },
  { id: 'outfit', label: 'Outfit' }, { id: 'voice', label: 'Voice' }, { id: 'style', label: 'Style' },
  { id: 'script', label: 'Script' }, { id: 'other', label: 'Other' },
];
const FIND_KEY = 'scene.kit.type';
const ASSETS_PAGE = 60;   // records of the catalogue shown at first, and how many more each time
const LONG = 160;         // characters of a value shown before "more"
const LOOK_AGAIN = 15000;   // while pictures wait to be described, the panel looks again this often (a few times)

export const kitUrl = (entry) => `/api/kit/${entry.id}/file`;

// The type of an entry made from a file dropped into a reference slot with this label (as the server reads it).
const SLOT_TYPES = [['character', /character|main character|second person|\bperson\b/i], ['location', /background|location/i],
  ['outfit', /outfit|costume|clothing/i], ['prop', /\bprop\b|product/i], ['voice', /voice/i], ['style', /\bstyle\b/i]];
export const typeForSlot = (label) => (SLOT_TYPES.find(([, words]) => words.test(label || '')) || ['other'])[0];

export function kitThumb(entry) {
  if (entry.kind === 'image') return el('img', { src: kitUrl(entry), alt: '', loading: 'lazy', draggable: 'false' });
  if (entry.kind === 'video') return el('video', { src: kitUrl(entry) + '#t=0.1', preload: 'metadata', muted: true });
  return el('span', { class: 'kit-glyph' }, icon(entry.kind === 'audio' ? 'audio' : 'book'));
}

const typeSelect = (current, onChange) => el('select', { class: 'kit-type', 'aria-label': 'Type', onchange: (e) => onChange(e.target.value) },
  KIT_TYPES.map((t) => el('option', { value: t.id, selected: t.id === current }, t.label)));

// Add a file, a canvas item or a script to a project's kit. file / item: what is added (a script has neither).
// Resolves with the new entry, or null if the dialog is closed.
export function addToKitDialog({ project = 0, file = null, item = null, script = false, type = '' } = {}) {
  if (!project) {   // a NeuralCore belongs to a project: there is none for all work
    alert(`The ${KIT} belongs to a project. Open a project from All projects and keep its characters, places and props there; each module keeps its own.`);
    return Promise.resolve(null);
  }
  return new Promise((resolve) => {
    let made = null;
    const guess = type || (script ? 'script' : file && /^audio\//.test(file.type) ? 'voice' : 'character');
    const name = el('input', { type: 'text', maxlength: 60, value: (file ? file.name.replace(/\.[^.]+$/, '') : item ? item.name : '').slice(0, 60),
      placeholder: script ? 'Ep 135' : 'Violet' });
    const kind = typeSelect(guess, () => {});
    const always = el('input', { type: 'checkbox' });
    const words = script && el('textarea', { rows: 10, placeholder: 'Paste the script here.' });
    const error = el('p', { class: 'error notice' });
    const save = async () => {
      if (!name.value.trim()) { error.textContent = 'Give it a name: the agent finds it by this name.'; name.focus(); return; }
      try {
        if (file) {
          const data = new FormData();
          data.append('file', file, file.name);
          data.append('name', name.value);
          data.append('type', kind.value);
          data.append('project_id', String(project || ''));
          if (always.checked) data.append('always', '1');
          made = await api('/api/kit', { method: 'POST', body: data });
        } else {
          made = await api('/api/kit', { method: 'POST', json: { project_id: project || null, name: name.value, type: kind.value, always: always.checked,
            ...(item ? { item: item.id } : { text: words.value }) } });
        }
        dialog.close();
      } catch (e) { error.textContent = e.message; }
    };
    const dialog = openDialog(
      el('h2', {}, script ? `Add a script to the ${KIT}` : `Add to the ${KIT}`),
      el('p', { class: 'muted' }, `The agent finds it by its name in every tab of this project, and Quick actions offers it in the slots it fits.`),
      field('Name', name), field('Type', kind), words && field('Script', words),
      !script && el('label', { class: 'check' }, always, el('span', {}, 'Always on: put it into every shot that has a place for it')),
      error,
      el('div', { class: 'dialog-buttons' },
        el('button', { class: 'btn', onclick: () => dialog.close() }, 'Cancel'),
        el('button', { class: 'btn primary', onclick: save }, 'Add')));
    dialog.addEventListener('close', () => resolve(made));
    name.focus();
    name.select();
  });
}

// "Keep the result in NeuralCore as …": a name and a type given before Generate, so what is made goes into the project's
// kit under that name when it is done (a character sheet made by hand, a location plate). A picture can be kept as any
// type but a voice; a sound only as a voice. show(kind): shown for the kind the workflow makes, hidden for the rest.
export function keepField() {
  const on = el('input', { type: 'checkbox', onchange: () => draw() });
  const name = el('input', { type: 'text', class: 'keep-name', maxlength: 60, placeholder: 'Name, e.g. Maya', 'aria-label': `Name in the ${KIT}` });
  const kind = el('select', { class: 'keep-type', 'aria-label': 'Type' });
  const row = el('div', { class: 'keep-row hidden' }, name, kind);
  const node = el('div', { class: 'keep-field hidden' }, el('label', { class: 'check keep-check' }, on, el('span', {}, `Keep the result in the ${KIT}`)), row);
  let makes = '';
  function draw() { row.classList.toggle('hidden', !on.checked); if (on.checked) name.focus(); }
  return {
    node,
    // inProject: whether the job is in a project; outside one there is no NeuralCore to keep it in
    show(kindMade, inProject = true) {
      makes = inProject ? kindMade : '';
      const types = !makes ? [] : kindMade === 'audio' ? ['voice'] : kindMade === 'image' ? ['character', 'location', 'prop', 'outfit', 'style'] : [];
      node.classList.toggle('hidden', !types.length);
      kind.replaceChildren(...types.map((t) => el('option', { value: t }, KIT_TYPES.find((x) => x.id === t).label)));
    },
    // what the job keeps ({"as", "name"}), or undefined when it keeps nothing
    value: () => (on.checked && name.value.trim() && makes ? { as: kind.value, name: name.value.trim() } : undefined),
    reset() { on.checked = false; name.value = ''; draw(); },
  };
}

// Pick an entry of the project's kit for a reference slot that takes `kind` (image, video or audio). Resolves with
// the entry, or null.
export function pickFromKit(kind, project = 0) {
  const fits = { image: ['image', 'video'], video: ['video'], audio: ['audio', 'video'] }[kind] || [kind];
  return new Promise(async (resolve) => {
    let entries = [];
    try { entries = (await api('/api/kit?project=' + (project || 0))).entries.filter((e) => fits.includes(e.kind)); } catch (e) { alert(e.message); return resolve(null); }
    let chosen = null;
    const dialog = openDialog(
      el('h2', {}, `From the ${KIT}`),
      entries.length
        ? el('div', { class: 'asset-grid' }, entries.map((entry) =>
          el('button', { type: 'button', class: 'asset', onclick: () => { chosen = entry; dialog.close(); } },
            el('div', { class: 'asset-thumb' }, kitThumb(entry)),
            el('div', { class: 'asset-name' }, entry.name),
            el('div', { class: 'muted' }, entry.type))))
        : el('p', { class: 'muted' }, `Nothing in this module's ${KIT} fits here yet. Add characters, locations and voices in the ${KIT} tab of the canvas.`),
      el('div', { class: 'dialog-buttons' }, el('button', { class: 'btn', onclick: () => dialog.close() }, 'Close')));
    dialog.addEventListener('close', () => resolve(chosen));
  });
}

const HAS_LOOKS = ['character', 'location', 'prop'];   // the types whose entries have looks (a location's: its times of day)

// How an entry hangs together with the others, in a few words for its row: "look of Maya · from sc 3", "2 looks", "mother of Dev".
function linksLine(entry, entries) {
  const byId = new Map(entries.map((e) => [e.id, e]));
  const parts = [];
  if (entry.look_of && byId.has(entry.look_of)) {
    parts.push(`${entry.type === 'location' ? 'time of day of' : 'look of'} ${byId.get(entry.look_of).name}` + (entry.from_scene ? ` · from sc ${entry.from_scene}` : ''));
  }
  const looks = entries.filter((e) => e.look_of === entry.id).length;
  if (looks) parts.push(`${looks} ${entry.type === 'location' ? (looks === 1 ? 'time of day' : 'times of day') : (looks === 1 ? 'look' : 'looks')}`);
  if (entry.palette) parts.push('palette');
  const kin = (entry.relations || []).filter((r) => byId.has(r.to)).length + entries.filter((e) => (e.relations || []).some((r) => r.to === entry.id)).length;
  if (kin) parts.push(`${kin} ${kin === 1 ? 'relative' : 'relatives'}`);
  return parts.join(' · ');
}

// The fields of how an entry hangs together: the entry it is a look (or a time of day) of, from which scene, a
// location's palette, a character's relatives. Returns {node, value()}; value() is what PUT /api/kit/<id> takes.
function linkFields(entry, entries) {
  const type = entry.type;
  if (!HAS_LOOKS.includes(type)) return { node: null, value: () => ({}) };
  const bases = entries.filter((e) => e.id !== entry.id && e.type === type && !e.look_of);
  const lookOf = el('select', {}, el('option', { value: '0' }, '— an entry of its own —'),
    ...bases.map((e) => el('option', { value: String(e.id), selected: e.id === entry.look_of }, e.name)));
  const variant = el('input', { maxlength: 40, value: entry.variant || '', placeholder: type === 'location' ? 'night, dawn, golden hour…' : 'torn sleeve, battle armour, as a child…' });
  const scene = el('input', { type: 'number', min: 0, max: 10000, value: entry.from_scene || '', placeholder: 'any' });
  const palette = el('input', { maxlength: 200, value: entry.palette || '', placeholder: 'cold steel-blue shadows, warm sodium highlights, muted and filmic' });
  const people = entries.filter((e) => e.id !== entry.id && e.type === 'character' && !e.look_of);
  const kin = el('div', { class: 'kit-kin' });
  const kinRow = (rel = { to: 0, relation: '', blood: true }) => {
    const who = el('select', {}, el('option', { value: '0' }, 'Who…'), ...people.map((e) => el('option', { value: String(e.id), selected: e.id === rel.to }, e.name)));
    const words = el('input', { maxlength: 30, value: rel.relation, placeholder: 'mother, brother, mother-in-law…', 'aria-label': 'How they are related' });
    const blood = el('select', { 'aria-label': 'By blood or in-law' }, el('option', { value: 'blood', selected: rel.blood }, 'blood'), el('option', { value: 'law', selected: !rel.blood }, 'in-law'));
    const line = el('div', { class: 'kit-kin-row' }, who, el('span', { class: 'muted' }, 'is their'), words, blood,
      el('button', { type: 'button', class: 'icon-btn', 'aria-label': 'Remove this relative', onclick: () => line.remove() }, '×'));
    line.value = () => ({ to: Number(who.value), relation: words.value.trim(), blood: blood.value === 'blood' });
    kin.append(line);
  };
  (entry.relations || []).forEach(kinRow);
  const isLook = () => lookOf.value !== '0';
  const kinField = type === 'character' && people.length ? el('div', {}, field('Relatives', kin),
    el('button', { type: 'button', class: 'btn small', onclick: () => kinRow() }, 'Add a relative')) : null;
  const node = el('div', { class: 'kit-links' }, el('h3', {}, 'How it fits together'),
    bases.length ? field(type === 'location' ? 'A time of day of' : 'A look of', lookOf) : null,
    field(type === 'location' ? 'Time of day' : 'The look', variant),
    type === 'character' ? field('Starts in scene', scene) : null,
    type === 'location' ? field('Palette', palette) : null,
    kinField);
  return {
    node,
    value: () => ({
      look_of: Number(lookOf.value) || 0, variant: variant.value,
      ...(type === 'character' ? { from_scene: Number(scene.value) || 0 } : {}),
      ...(type === 'location' ? { palette: palette.value } : {}),
      ...(kinField && !isLook() ? { relations: [...kin.children].map((line) => line.value()).filter((r) => r.to && r.relation) } : {}),
    }),
  };
}

// The card of an entry: what it shows (the model's words, or the user's), how to use it, and how it fits with the rest.
function cardDialog(entry, onSaved, entries = []) {
  const about = el('textarea', { rows: 5, maxlength: 600 }, entry.about || '');
  const use = el('textarea', { rows: 3, maxlength: 600, placeholder: 'When and how to use it, e.g. "only in the night scenes".' }, entry.use_note || '');
  const links = linkFields(entry, entries);
  const error = el('p', { class: 'error notice' });
  const dialog = openDialog(
    el('h2', {}, entry.name),
    el('p', { class: 'muted' }, 'What it shows is written by the agent\'s model when it is added. Correct it here: your words win.'),
    field('What it shows', about), field('How to use it', use), links.node, error,
    el('div', { class: 'dialog-buttons' },
      el('button', { class: 'btn', onclick: () => dialog.close() }, 'Cancel'),
      el('button', { class: 'btn primary', onclick: async () => {
        try { await api('/api/kit/' + entry.id, { method: 'PUT', json: { about: about.value, use_note: use.value, ...links.value() } }); dialog.close(); onSaved(); } catch (e) { error.textContent = e.message; }
      } }, 'Save')));
}

// projectId(): the current project or module, or 0. selected(): the one canvas item selected, or null. onChange(): the
// kit changed. The panel is NeuralCore's memory of the module open now, as a tree in the manner of Frameo's: the cast
// (this module's entries, with their controls), the assets (every file of the module, by its
// record) and the notes the agent and its skills keep. "You" is what the agent remembers of the user everywhere.
export function kitPanel({ projectId = () => 0, selected = () => null, onChange = () => {} } = {}) {
  let found = null;            // what /api/kit gave (the cast's entries with their controls), or null while it loads
  let memory = null;           // what /api/core/memory gave, or {error}
  let you = null;              // /api/remembered
  let loadedAt = 0;
  let looks = 0;               // how many times it looked again for descriptions
  let lookTimer = null;
  let filter = localStorage.getItem(FIND_KEY) || '';
  let scope = 'module';
  let assetsShown = ASSETS_PAGE;
  const open = new Set(['cast']);   // the folders and cards open now, by path
  const raw = new Set();             // the top folders shown as their JSON
  const longOpen = new Set();        // the long values shown whole
  const stamp = el('span', { class: 'slate-text' });
  const scopes = el('div', { class: 'kit-views' });
  const search = el('input', { type: 'search', class: 'kit-search', placeholder: 'Search by name or what it shows', 'aria-label': `Search the ${KIT}`, oninput: () => draw() });
  const kinds = el('select', { class: 'kit-filter', 'aria-label': 'Type', onchange: (e) => { filter = e.target.value; localStorage.setItem(FIND_KEY, filter); draw(); } },
    el('option', { value: '' }, 'All types'), KIT_TYPES.map((t) => el('option', { value: t.id, selected: t.id === filter }, t.label)));
  const tools = el('div', { class: 'kit-tools' }, search, kinds);
  const upload = el('input', { type: 'file', hidden: true, accept: 'image/*,video/*,audio/*,.heic,.heif,.avif,.txt,.md,.docx,.pdf,.srt,.json',
    onchange: async (e) => { const file = e.target.files[0]; e.target.value = ''; if (file && await addToKitDialog({ project: projectId(), file })) changed(); } });
  // An asset sheet (a CSV a spreadsheet exports: type, name, image link and notes a row): every row's picture is fetched.
  const sheetPick = el('input', { type: 'file', hidden: true, accept: '.csv,.tsv,text/csv',
    onchange: (e) => { const file = e.target.files[0]; e.target.value = ''; if (file) importSheet(file); } });
  const addButton = el('button', { class: 'btn small primary', type: 'button', title: 'Add to the cast', onclick: (e) => openAdd(e.currentTarget) }, icon('plus'), 'Add');
  const body = el('div', { class: 'kit-body' });
  const node = el('div', { class: 'kit-panel memory-panel' },
    el('div', { class: 'memory-head' }, el('b', {}, 'Memory'), el('span', { style: 'flex:1' }), stamp,
      el('button', { class: 'icon-btn', title: 'Refresh', 'aria-label': 'Refresh', onclick: () => load() }, '↻'), addButton, upload, sheetPick),
    scopes, body);

  function openAdd(anchor) {
    const one = selected();
    addMenu(anchor, [
      { icon: 'upload', label: 'Upload a file', hint: 'picture, video, sound or script', run: () => upload.click() },
      { icon: 'grid', label: one ? `“${one.name}” from the canvas` : 'Select an item on the canvas first', run: async () => {
        if (!one) return;
        if (await addToKitDialog({ project: projectId(), item: one })) changed();
      } },
      { icon: 'book', label: 'Paste a script', run: async () => { if (await addToKitDialog({ project: projectId(), script: true })) changed(); } },
      { icon: 'queue', label: 'Import an asset sheet', hint: 'CSV: type, name, image link, notes', run: () => sheetPick.click() },
    ]);
  }

  async function importSheet(file) {
    const data = new FormData();
    data.append('file', file, file.name);
    data.append('project_id', String(projectId() || ''));
    stamp.textContent = 'fetching the sheet’s pictures…';
    let done;
    try { done = await api('/api/kit/sheet', { method: 'POST', body: data }); } catch (e) { stamp.textContent = ''; alert(e.message); return; }
    changed();
    const fresh = done.added.filter((a) => a.new).length;
    const problems = [...done.failed.map((f) => `Row ${f.row}, “${f.name}”: ${f.reason}`),
      ...done.left_out.map((f) => `Row ${f.row}${f.name ? `, “${f.name}”` : ''}: left out, ${f.reason}`)];
    const dialog = openDialog(
      el('h2', {}, `Brought into the ${KIT}`),
      el('p', {}, `${fresh} new ${fresh === 1 ? 'entry' : 'entries'}` + (done.added.length > fresh ? `, ${done.added.length - fresh} already here` : '') +
        (done.looks.length ? `, ${done.looks.length} linked as looks of another` : '') + '.'),
      problems.length ? el('ul', {}, problems.map((line) => el('li', {}, line))) : null,
      el('div', { class: 'dialog-buttons' }, el('button', { class: 'btn primary', onclick: () => dialog.close() }, 'OK')));
  }

  async function change(entry, json) {
    try { Object.assign(entry, await api('/api/kit/' + entry.id, { method: 'PUT', json })); } catch (e) { alert(e.message); }
    changed(false);
  }

  async function remove(entry) {
    if (!await ask({ title: `Take “${entry.name}” out of the cast?`, danger: true, confirm: 'Take it out',
      message: 'The agent will no longer know it by this name in this module.' })) return;
    try { await api('/api/kit/' + entry.id, { method: 'DELETE' }); } catch (e) { alert(e.message); }
    changed();
  }

  // Drop an entry before another: the whole cast is saved in its new order.
  async function moveBefore(entry, target) {
    const list = found.entries.filter((e) => e.id !== entry.id);
    const at = target ? list.findIndex((e) => e.id === target.id) : list.length;
    list.splice(at < 0 ? list.length : at, 0, entry);
    found.entries = list;
    draw();
    try { found.entries = (await api('/api/kit/order', { method: 'POST', json: { project_id: projectId() || null, ids: list.map((e) => e.id) } })).entries; } catch (e) { alert(e.message); }
    changed(false);
  }

  function changed(reload = true) { onChange(); if (reload) load(); else draw(); }

  // Drag an entry by its grip: it follows the pointer, the others slide up or down to show where it will go, and when
  // it is let go the list is drawn in its new order with every row gliding from where it was.
  const slide = (row) => (y) => { row.style.translate = y ? `0 ${y}px` : ''; };
  function dragRow(e, entry) {
    if (e.button !== 0) return;
    e.preventDefault();
    const grip = e.currentTarget;
    const rows = [...node.querySelectorAll('.kit-row')];
    const row = grip.closest('.kit-row');
    const index = rows.indexOf(row);
    if (index < 0) return;
    const rects = rows.map((r) => r.getBoundingClientRect());
    const step = rects.length > 1 ? (index < rects.length - 1 ? rects[index + 1].top - rects[index].top : rects[index].top - rects[index - 1].top) : 0;
    const low = rects[0].top - rects[index].top;
    const high = rects[rects.length - 1].top - rects[index].top;
    const shifts = rows.map((r) => new Spring(0, slide(r)));
    const aims = rows.map(() => 0);
    const from = e.clientY;
    let to = index;
    grip.setPointerCapture(e.pointerId);
    row.classList.add('lifted');
    const onMove = (ev) => {
      const dy = ev.clientY - from;
      const y = dy < low ? low - rubberband(low - dy, 120) : dy > high ? high + rubberband(dy - high, 120) : dy;
      shifts[index].set(y);
      const middle = rects[index].top + y + rects[index].height / 2;
      to = rects.filter((r, i) => i !== index && r.top + r.height / 2 < middle).length;
      rows.forEach((r, i) => {
        if (i === index) return;
        const aim = i > index && i <= to ? -step : i < index && i >= to ? step : 0;
        if (aim !== aims[i]) { aims[i] = aim; shifts[i].to(aim, { response: 0.3 }); }
      });
    };
    const end = () => {
      grip.removeEventListener('pointermove', onMove);
      grip.removeEventListener('pointerup', end);
      grip.removeEventListener('pointercancel', end);
      shifts.forEach((s) => s.stop());
      if (to === index) {
        shifts.forEach((s) => s.to(0, { response: 0.3, done: () => row.classList.remove('lifted') }));
        return;
      }
      // The entry it now goes before: the one shown at that place, or, at the end of what is shown, the one after it.
      const others = rows.filter((r) => r !== row).map((r) => r.kitEntry);
      const last = others[others.length - 1];
      const target = others[to] || found.entries.filter((x) => x.id !== entry.id)[found.entries.filter((x) => x.id !== entry.id).indexOf(last) + 1] || null;
      const was = new Map(rows.map((r) => [r.kitEntry.id, r.getBoundingClientRect().top]));
      moveBefore(entry, target);   // draws the list again at once, then saves the order
      for (const r of node.querySelectorAll('.kit-row')) {
        const dy = (was.get(r.kitEntry.id) ?? r.getBoundingClientRect().top) - r.getBoundingClientRect().top;
        if (dy) new Spring(dy, slide(r)).to(0, { response: 0.3, damping: r.kitEntry.id === entry.id ? 0.8 : 1 });
      }
    };
    grip.addEventListener('pointermove', onMove);
    grip.addEventListener('pointerup', end);
    grip.addEventListener('pointercancel', end);
  }

  function row(entry) {
    const name = el('input', { class: 'kit-name', value: entry.name, maxlength: 60, 'aria-label': 'Name',
      onchange: (e) => { if (e.target.value.trim()) change(entry, { name: e.target.value }); } });
    const line = el('div', { class: 'kit-row' + (entry.named ? '' : ' unnamed') + (entry.always ? ' always' : '') },
      el('span', { class: 'kit-grip', title: 'Drag to change the order', 'aria-hidden': 'true', onpointerdown: (e) => dragRow(e, entry) }, '⋮⋮'),
      el('span', { class: 'memory-thumb kit-thumb' }, kitThumb(entry)),
      el('div', { class: 'kit-main' },
        el('div', { class: 'kit-line' }, name, !entry.named && el('span', { class: 'kit-flag', title: 'The agent will ask who or what this is' }, 'needs a name')),
        el('div', { class: 'kit-line' }, typeSelect(entry.type, (type) => change(entry, { type })),
          entry.kind !== 'text' && el('label', { class: 'kit-always', title: 'Put it into every shot that has a place for it' },
            el('input', { type: 'checkbox', checked: entry.always, onchange: (e) => change(entry, { always: e.target.checked }) }),
            el('span', {}, 'Always on'))),
        el('button', { type: 'button', class: 'kit-about small muted', title: 'What it shows, how to use it, and how it fits with the rest', onclick: () => cardDialog(entry, load, found.entries) },
          entry.use_note || entry.about || (entry.kind === 'image' || entry.kind === 'video' ? 'Being looked at…' : 'Add what it is')),
        linksLine(entry, found.entries) && el('div', { class: 'kit-links-line small muted' }, linksLine(entry, found.entries))),
      el('button', { class: 'icon-btn kit-remove', title: 'Take it out of the cast',
        'aria-label': `Take ${entry.name} out of the cast`, onclick: () => remove(entry) }, '×'));
    line.kitEntry = entry;   // the entry a dragged row stands for
    return line;
  }

  // -- the tree ---------------------------------------------------------------------------------------------------------

  // The leaves of the module's notes as a tree: each node {kids: Map, leaf}, a leaf {path, value, writer, updated}.
  function treeOf(leaves) {
    const root = { kids: new Map(), leaf: null };
    for (const leaf of leaves) {
      let at = root;
      for (const part of leaf.path.split('/').filter(Boolean)) {
        if (!at.kids.has(part)) at.kids.set(part, { kids: new Map(), leaf: null });
        at = at.kids.get(part);
      }
      at.leaf = leaf;
    }
    return root;
  }

  const isNode = (x) => x && x.kids instanceof Map;
  const isObject = (x) => x !== null && typeof x === 'object';
  const natural = (a, b) => a[0].localeCompare(b[0], undefined, { numeric: true });
  // What is inside a node of the tree or a value kept in a leaf, as [name, child] pairs; null for a plain value.
  function partsOf(x) {
    if (isNode(x)) {
      if (x.kids.size) return [...x.kids.entries()].sort(natural);
      return x.leaf && isObject(x.leaf.value) ? partsOf(x.leaf.value) : null;
    }
    if (Array.isArray(x)) return x.map((v, i) => [String(i + 1), v]);
    return isObject(x) ? Object.entries(x) : null;
  }
  const valueOf = (x) => (isNode(x) ? (x.leaf ? x.leaf.value : undefined) : x);
  const plain = (x) => partsOf(x) === null;
  const jsonOf = (x) => (isNode(x) ? (x.kids.size ? Object.fromEntries(partsOf(x).map(([k, v]) => [k, jsonOf(v)])) : x.leaf.value) : x);
  const latest = (x) => (isNode(x) ? Math.max(x.leaf ? x.leaf.updated || 0 : 0, ...[...x.kids.values()].map(latest)) : 0);
  const kilobytes = (x) => `${(new Blob([JSON.stringify(x)]).size / 1024).toFixed(1)} KB`;

  // A record of the catalogue by its id: the memory names files as "$state:/assets/<id>/url".
  const records = () => new Map(((memory && memory.assets && memory.assets.records) || []).map((r) => [r.id, r]));
  const REF = /^\$state:\/assets\/([0-9a-f]{12})(?:\/url)?$/;

  function thumbOf(record) {
    if (!record) return null;
    if (record.kind !== 'image' && record.kind !== 'video') return el('span', { class: 'mem-thumb glyph' }, icon(record.kind === 'audio' ? 'audio' : 'book'));
    const src = record.item ? `/api/library/${record.item}/poster` : record.url;
    return el('span', { class: 'mem-thumb' + (record.kind === 'video' ? ' video' : '') },
      el('img', { src, alt: '', loading: 'lazy', onerror: (e) => e.target.remove() }), record.kind === 'video' && icon('play'));
  }

  function copyButton(text, what) {
    return el('button', { type: 'button', class: 'icon-btn mem-act', title: `Copy ${what}`, 'aria-label': `Copy ${what}`, onclick: (e) => {
      e.stopPropagation();
      navigator.clipboard?.writeText(text).catch(() => {});
    } }, icon('copy'));
  }

  // One value as Frameo shows it: a number in colour, a reference to a file with its picture, a long text cut short
  // with "more".
  function valueCell(value, path, known) {
    if (typeof value === 'number') return el('span', { class: 'mem-val num' }, String(value));
    if (typeof value === 'boolean' || value === null) return el('span', { class: 'mem-val num' }, String(value));
    const text = String(value);
    const ref = text.match(REF);
    if (ref) {
      const record = known.get(ref[1]);
      return el('span', { class: 'mem-val' }, el('span', {}, text), record && thumbOf(record));
    }
    if (text.length <= LONG || longOpen.has(path)) return el('span', { class: 'mem-val' }, text);
    return el('span', { class: 'mem-val' }, text.slice(0, LONG).trimEnd() + '…',
      el('button', { type: 'button', class: 'mem-more', onclick: () => { longOpen.add(path); draw(); } }, 'more'));
  }

  // The line under a card's name: its first plain value; the names of the rest go beside it as chips.
  function summaryOf(parts) {
    const first = parts.findIndex(([, v]) => plain(v) && valueOf(v) !== undefined && valueOf(v) !== '');
    const line = first < 0 ? '' : String(valueOf(parts[first][1]));
    const rest = parts.filter((_, i) => i !== first).map(([k]) => k);
    return { line, chips: rest };
  }

  function chips(names) {
    if (!names.length) return null;
    const shown = names.slice(0, 4);
    return el('div', { class: 'mem-chips' }, shown.join(' · ') + (names.length > shown.length ? ` · +${names.length - shown.length}` : ''));
  }

  // Edit the leaf a value is kept in (its whole JSON), or delete it.
  function editLeaf(leaf) {
    const box = el('textarea', { rows: 10, class: 'mono' }, JSON.stringify(leaf.value, null, 2));
    const error = el('p', { class: 'error notice' });
    const dialog = openDialog(
      el('h2', {}, leaf.path),
      el('p', { class: 'muted' }, `Kept by ${leaf.writer || 'someone'} ${leaf.updated ? ago(leaf.updated) : ''}. Every agent tab of this module reads it from here: your change wins.`),
      field('Value (JSON)', box), error,
      el('div', { class: 'dialog-buttons' },
        el('button', { class: 'btn danger', onclick: async () => {
          if (!await ask({ title: `Delete ${leaf.path}?`, danger: true, confirm: 'Delete' })) return;
          try { await api(`/api/core/state?project=${projectId()}&path=${encodeURIComponent(leaf.path)}`, { method: 'DELETE' }); dialog.close(); load(); }
          catch (e) { error.textContent = e.message; }
        } }, 'Delete'),
        el('span', { style: 'flex:1' }),
        el('button', { class: 'btn', onclick: () => dialog.close() }, 'Cancel'),
        el('button', { class: 'btn primary', onclick: async () => {
          let value;
          try { value = JSON.parse(box.value); } catch { error.textContent = 'That is not JSON: text goes in "quotes".'; return; }
          try { await api('/api/core/state', { method: 'PUT', json: { project_id: projectId(), path: leaf.path, value } }); dialog.close(); load(); }
          catch (e) { error.textContent = e.message; }
        } }, 'Save')));
  }

  // A row of a card's grid: the name, then a plain value, a smaller grid (a group of plain values) or a card of its own.
  function gridRow(name, child, path, owner, known) {
    const leaf = isNode(child) && child.leaf ? child.leaf : owner;
    const parts = partsOf(child);
    if (parts === null) {
      const value = valueOf(child);
      return el('div', { class: 'mem-row' }, el('span', { class: 'mem-key' }, name), valueCell(value, path, known),
        el('span', { class: 'mem-acts' }, copyButton(typeof value === 'string' ? value : JSON.stringify(value), 'the value'),
          leaf && memory.writable && el('button', { type: 'button', class: 'icon-btn mem-act', title: 'Change it', 'aria-label': `Change ${path}`, onclick: () => editLeaf(leaf) }, icon('pencil'))));
    }
    if (parts.every(([, v]) => plain(v)))
      return el('div', { class: 'mem-row' }, el('span', { class: 'mem-key' }, name),
        el('div', { class: 'mem-grid' }, parts.map(([k, v]) => gridRow(k, v, `${path}/${k}`, leaf, known))));
    return el('div', { class: 'mem-row' }, el('span', { class: 'mem-key' }, name),
      el('div', { class: 'mem-cards' }, parts.map(([k, v]) => card(k, v, `${path}/${k}`, leaf, known))));
  }

  // A card: its name, the line under it and the chips of the rest; open, the grid of what it holds.
  function card(name, child, path, owner, known) {
    const parts = partsOf(child);
    if (parts === null) return gridRow(name, child, path, owner, known);
    const leaf = isNode(child) && child.leaf ? child.leaf : owner;
    const { line, chips: rest } = summaryOf(parts);
    const isOpen = open.has(path);
    const ref = line.match(REF);
    const head = el('div', { class: 'mem-card-head', onclick: () => { isOpen ? open.delete(path) : open.add(path); draw(); } },
      ref ? thumbOf(known.get(ref[1])) : null,
      el('div', { class: 'mem-card-text' }, el('b', {}, name), line && el('div', { class: 'mem-summary' }, line), !isOpen && chips(rest)),
      el('span', { class: 'mem-acts' }, copyButton('$state:' + path, 'its path'),
        leaf && memory.writable && el('button', { type: 'button', class: 'icon-btn mem-act', title: 'Change it', 'aria-label': `Change ${path}`, onclick: (e) => { e.stopPropagation(); editLeaf(leaf); } }, icon('pencil'))),
      el('span', { class: 'mem-chev' + (isOpen ? ' open' : '') }, icon('right')));
    return el('div', { class: 'mem-card' + (isOpen ? ' open' : '') }, head,
      isOpen && el('div', { class: 'mem-grid' }, parts.map(([k, v]) => gridRow(k, v, `${path}/${k}`, leaf, known))));
  }

  // A folder at the top of the memory: its name, how many things it holds, how large it is and when it last changed.
  function folder(name, count, size, when, inner, rawJson) {
    const isOpen = open.has(name);
    return el('section', { class: 'mem-folder' + (isOpen ? ' open' : '') },
      el('div', { class: 'mem-folder-head', onclick: () => { isOpen ? open.delete(name) : open.add(name); draw(); } },
        el('span', { class: 'mem-chev' + (isOpen ? ' open' : '') }, icon('right')), el('b', {}, name),
        el('span', { class: 'slate-text' }, ` · ${count} ${count === 1 ? 'item' : 'items'}`), el('span', { style: 'flex:1' }),
        isOpen && rawJson !== undefined && el('button', { type: 'button', class: 'mem-raw-btn' + (raw.has(name) ? ' on' : ''), onclick: (e) => {
          e.stopPropagation(); raw.has(name) ? raw.delete(name) : raw.add(name); draw();
        } }, 'raw'),
        el('span', { class: 'slate-text' }, [size, when ? ago(when) : ''].filter(Boolean).join(' · '))),
      isOpen && (raw.has(name) && rawJson !== undefined ? el('pre', { class: 'mem-raw' }, JSON.stringify(rawJson, null, 2)) : inner()));
  }

  function castFolder() {
    const words = search.value.trim().toLowerCase();
    const entries = found ? found.entries : [];
    const shown = entries.filter((e) => (!filter || e.type === filter) && (!words || `${e.name} ${e.about} ${e.use_note}`.toLowerCase().includes(words)));
    const on = shown.filter((e) => e.always);
    const rest = shown.filter((e) => !e.always);
    return folder('cast', entries.length, memory && memory.cast ? kilobytes(memory.cast) : '', 0, () => el('div', { class: 'mem-inner' }, ...[
      el('p', { class: 'small muted' }, 'This module\'s characters, places and props; other modules have their own. Always on goes into every shot that has a place for it.'),
      entries.length > 3 && tools,
      !found && el('p', { class: 'small muted' }, 'Loading…'),
      found && !entries.length && el('p', { class: 'small muted' }, 'Nothing yet. Add a character, a place or a prop with Add, or name one in a message to the agent: "Maya - @1".'),
      on.length > 0 && el('div', { class: 'kit-group' }, el('h3', {}, 'Always on', el('span', { class: 'slate-text' }, ' · in every shot, in this order')), ...on.map(row)),
      rest.length > 0 && el('div', { class: 'kit-group' }, on.length > 0 && el('h3', {}, 'The rest'), ...rest.map(row)),
      entries.length > 0 && !shown.length && el('p', { class: 'small muted' }, 'Nothing matches.')].filter(Boolean)), memory && memory.cast);
  }

  function recordCard(record, known) {
    const path = '/assets/' + record.id;
    const isOpen = open.has(path);
    const line = record.prompt || record.visual || record.shows || record.filename || record.made || '';
    const fields = Object.keys(record).filter((k) => !['id', 'name', 'item', 'entry'].includes(k));
    const head = el('div', { class: 'mem-card-head', onclick: () => { isOpen ? open.delete(path) : open.add(path); draw(); } },
      thumbOf(record),
      el('div', { class: 'mem-card-text' }, el('div', {}, el('b', {}, record.name), el('span', { class: 'mem-id' }, record.id)),
        line && el('div', { class: 'mem-summary' }, line), !isOpen && chips(fields)),
      el('span', { class: 'mem-acts' }, copyButton(`$state:/assets/${record.id}/url`, 'its reference')),
      el('span', { class: 'mem-chev' + (isOpen ? ' open' : '') }, icon('right')));
    return el('div', { class: 'mem-card' + (isOpen ? ' open' : '') }, head,
      isOpen && el('div', { class: 'mem-grid' }, fields.map((k) => gridRow(k, record[k], `${path}/${k}`, null, known))));
  }

  function assetsFolder(known) {
    const all = memory.assets.records;
    return folder('assets', memory.assets.total, kilobytes(all), all.length ? Date.parse(all[0].made) / 1000 : 0, () => el('div', { class: 'mem-inner' },
      !all.length && el('p', { class: 'small muted' }, 'Nothing made or brought into this module yet.'),
      ...all.slice(0, assetsShown).map((r) => recordCard(r, known)),
      all.length > assetsShown && el('button', { class: 'btn small', onclick: () => { assetsShown += ASSETS_PAGE; draw(); } }, `Show more (${all.length - assetsShown} left)`)), all);
  }

  function noteFolder(name, child, known) {
    const parts = partsOf(child) || [];
    const json = jsonOf(child);
    return folder(name, parts.length, kilobytes(json), latest(child), () => el('div', { class: 'mem-inner' },
      parts.length ? parts.map(([k, v]) => card(k, v, `/${name}/${k}`, isNode(child) ? child.leaf : null, known))
        : gridRow(name, child, '/' + name, null, known)), json);
  }

  function drawModule() {
    if (!projectId()) {
      body.replaceChildren(el('div', { class: 'kit-empty' }, el('p', {}, 'Memory belongs to a module. Open a project, or one of its modules, and what the agent keeps for it shows here.')));
      return;
    }
    if (!memory) { body.replaceChildren(el('p', { class: 'small muted' }, 'Loading…')); return; }
    if (memory.error) { body.replaceChildren(el('p', { class: 'error small' }, memory.error)); return; }
    const known = records();
    const notes = treeOf(memory.leaves);
    body.replaceChildren(...[
      el('p', { class: 'small muted memory-lead' }, 'What this module keeps: every agent tab of it and everyone in the project reads the same memory. Other modules keep their own.'),
      castFolder(), assetsFolder(known),
      ...[...notes.kids.entries()].sort(natural).map(([name, child]) => noteFolder(name, child, known)),
      !notes.kids.size && el('p', { class: 'small muted' }, 'No notes yet. The agent writes its plan, decisions and progress here as it works.')].filter(Boolean));
  }

  // What the agent remembers of the user across all their projects (preferences, what they keep using): each can go.
  function drawYou() {
    if (!you) { body.replaceChildren(el('p', { class: 'small muted' }, 'Loading…')); return; }
    if (you.error) { body.replaceChildren(el('p', { class: 'error small' }, you.error)); return; }
    body.replaceChildren(
      el('p', { class: 'small muted memory-lead' }, 'What the agent remembers of you in every project: how you like to work and what you keep using. It never overrides what you ask.'),
      you.entries.length ? el('div', { class: 'mem-inner' }, you.entries.map((entry) => el('div', { class: 'mem-card' },
        el('div', { class: 'mem-card-head' }, el('div', { class: 'mem-card-text' }, el('b', {}, entry.key), el('div', { class: 'mem-summary' }, entry.value)),
          el('span', { class: 'mem-acts' }, el('button', { class: 'icon-btn mem-act', title: 'Forget it', 'aria-label': `Forget ${entry.key}`, onclick: async () => {
            try { await api('/api/remembered?key=' + encodeURIComponent(entry.key), { method: 'DELETE' }); load(); } catch (e) { alert(e.message); }
          } }, icon('trash')))))))
        : el('p', { class: 'small muted' }, 'Nothing yet. Tell the agent how you like to work ("I always make Reels") and it keeps it.'));
  }

  function draw() {
    stamp.textContent = loadedAt ? 'refreshed ' + ago(loadedAt / 1000) : '';
    scopes.replaceChildren(segmented([{ id: 'module', label: 'This module', hint: 'What this module keeps' },
      { id: 'you', label: 'You', hint: 'What the agent remembers of you in every project' }], scope, (id) => { scope = id; draw(); load(); }));
    addButton.classList.toggle('hidden', !projectId() || scope !== 'module');
    if (scope === 'you') drawYou(); else drawModule();
  }

  async function load() {
    if (scope === 'you') {
      try { you = await api('/api/remembered'); } catch (e) { you = { error: e.message }; }
      loadedAt = Date.now();
      draw();
      return;
    }
    if (!projectId()) { found = null; memory = null; draw(); return; }
    try {
      [found, memory] = await Promise.all([api('/api/kit?project=' + projectId()), api('/api/core/memory?project=' + projectId())]);
      loadedAt = Date.now();
    } catch (e) {
      memory = { error: e.message };
    }
    draw();
    // pictures are described in the background as they come in: look again a few times while some wait
    clearTimeout(lookTimer);
    const waiting = found && found.entries.some((e) => !e.about && (e.kind === 'image' || e.kind === 'video'));
    if (waiting && looks < 4) { looks += 1; lookTimer = setTimeout(() => { if (node.isConnected) load(); }, LOOK_AGAIN); } else if (!waiting) looks = 0;
  }

  draw();
  return { node, load, reload: () => { found = null; memory = null; draw(); return load(); }, focus: () => { open.add('cast'); draw(); search.focus(); },
    count: () => (found ? found.entries.length : null), destroy: () => clearTimeout(lookTimer) };
}
