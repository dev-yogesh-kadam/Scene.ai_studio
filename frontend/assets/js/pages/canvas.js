// The Canvas page: every finished item as a frame on an endless board. A panel on the right makes new work,
// either directly (Quick action) or through the agent.
// Each row is a shot: new work starts a row, work made from a frame joins that frame's row. Frames can be
// dragged between rows, and the rows are remembered per project. Work in progress shows as a frame the Gate runs around.

import { api } from '../api.js';
import { clapper, creditMark, el, flight, icon, reel, runningGate, segmented, still, tabTitle } from '../dom.js';
import { refreshJobs, store, subscribe } from '../store.js';
import { openViewer, reuseSeed, seedOf } from '../components/media.js';
import { shareDialog } from '../components/share.js';
import { bulkPanel } from '../components/bulk.js';
import { quickActions } from '../components/quick.js';
import { agentTabs } from '../components/agent-tabs.js';
import { KIT, addToKitDialog, kitPanel } from '../components/kit.js';
import { go, placePath, showAddress } from '../nav.js';
import { Spring, project as carry, rubberband, tracker } from '../spring.js';

const FRAME = 240;      // width of every frame, in canvas units
const SLATE = 24;       // room under a frame for its line of facts
const LABEL = 144;      // room left of a row for the name of its shot
const GAP = 48;
const SNAP = 8;
const MIN_ZOOM = 0.1;
const MAX_ZOOM = 3;   // 300%: close enough to check a face or a hand
const ACTIVE = ['queued', 'running'];
// A job that failed stays on the canvas, where its result would have been, saying why, for this long: a frame that just
// vanished would look like the studio losing work.
const FAILED_SHOWN = 24 * 3600;
const PANEL = 380;      // the width the panel starts with; its left edge can be dragged
const PANEL_MIN = 320;
const PANEL_MAX = 960;
const TABS = [{ id: 'quick', label: 'Quick actions', icon: 'bolt' }, { id: 'agent', label: 'Agent', icon: 'chat' },
  { id: 'kit', label: KIT, icon: 'memory' }, { id: 'bulk', label: 'Bulk generation', icon: 'grid', admin: true }];

// The boards left of the shots, left to right: the finished cut, then the project's NeuralCore by type. A picture that is a
// NeuralCore entry, or a finished cut, sits on its board and not in a shot row.
const BOARDS = [['outputs', 'Outputs'], ['character', 'Characters'], ['background', 'Locations'], ['prop', 'Props'], ['outfit', 'Outfits'],
  ['style', 'Styles'], ['voice', 'Voices'], ['script', 'Scripts'], ['other', 'Other']];
const BOARD_LABEL = Object.fromEntries(BOARDS);
const FINAL_CUT = 'edit/assemble';
const BOARD_PAD = 20;     // inside a board, around its frames
const BOARD_HEAD = 64;    // the board's title, with room for it to grow as the canvas zooms out
const ENTRY_NAME = 22;    // the name of an entry, above its frame

const clamp = (n, low, high) => Math.max(low, Math.min(high, n));
const heightOf = (item) => {
  const c = (item && item.context) || {};
  return Math.round(FRAME * (c.width && c.height ? c.height / c.width : 9 / 16));
};
// A frame's place in its shot, counted as takes from the left; a take on a stack says which of how many it is.
const take = (spot) => spot.label || `Take ${Math.round(spot.x / (FRAME + GAP)) + 1}`;
// The number of the story shot a job was made for (its settings' shot_number, see backend/scene/placement.py), or null.
// Results with one sit in the row of that shot, rows in order of their numbers, and a retake stacks on the shot.
const shotNumber = (settings) => { const n = settings && settings.shot_number; return Number.isInteger(n) && n > 0 ? n : null; };
const STACK_STEP = 6;     // how far each earlier take peeks out from behind the one on top, up and to the right
const STACK_SHOWN = 3;    // earlier takes drawn behind it; more are there, one switch away
const elapsed = (job) => {
  const s = Math.max(0, Math.round(Date.now() / 1000 - (job.started || Date.now() / 1000)));
  return String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
};

export function render(view) {
  view.classList.add('full');
  let items = [];
  let projects = [];
  let project = Number(localStorage.getItem('scene.project')) || 0;   // 0 = everything
  // rows: [{id, name, keys, shot?}], one per shot, top to bottom. A key is a generation id, or 'job:<id>' while it is being
  // made. shot: the shot number of a row the agent's numbered shots made. picks: which take of a stack the user put on top,
  // {stack key: {key, count}}; a new take (count changes) goes on top again.
  let layout = { rows: [], count: 0, picks: {} };
  let placed = { boards: [] };    // named boards and their stacks, as finished jobs placed them (GET /api/library/placement)
  let ready = false;              // false until the saved layout is loaded: nothing may be placed before that
  const cam = { x: 96, y: 96, k: 1 };
  const selected = new Set();     // generation ids
  const spots = new Map();        // key -> {x, y, h}: where its row puts each frame
  let bands = [];                 // the rows as drawn: {row, y, h}
  let boardBox = { left: 0, width: 0 };   // where the board of shots is across, for the line that marks a new shot
  const boxes = new Map();        // what is on the canvas now: key -> {key, x, y, h, node}
  const jobFrames = new Map();    // job id -> the parts of its frame that change while it runs
  let agentJobs = new Set();      // jobs the agent started: their frames are drawn in the agent's colour

  const itemLayer = el('div');
  const jobLayer = el('div');
  const labelLayer = el('div');
  const fileLayer = el('div');    // NeuralCore entries that are files, not library items: shown on their board
  const world = el('div', { class: 'canvas-world' }, labelLayer, fileLayer, itemLayer, jobLayer);
  let kitEntries = [];            // the project's NeuralCore
  const onBoard = new Map();      // library item id -> {board, name}: it sits on a board, not in a shot row
  let boardCards = [];            // the boards as drawn: {label, x, y, w, h, names: [{text, x, y}]}
  const stage = el('div', { class: 'canvas-stage' }, world);
  // The canvas shows one project, the one opened from All projects; its name is shown, and it does not switch.
  const picker = el('b', { class: 'canvas-project', title: 'This project. Open another from All projects.' });
  const count = el('span', { class: 'slate-text' });
  const timelineLink = el('a', { class: 'btn small quiet', href: '/timeline', title: 'Put this project\'s videos in order' }, 'Timeline');
  const context = el('div', { class: 'float canvas-context hidden' });
  const zoomLabel = el('button', { class: 'btn small quiet canvas-zoom', title: 'Zoom to 100% (0)', onclick: () => zoomTo(1) });
  const map = el('div', { class: 'minimap hidden', 'aria-hidden': 'true' });
  const hint = el('p', { class: 'canvas-hint muted' }, 'Use the panel on the right to make a shot. Everything you make lands here.');
  // The balance, at the top right like on every page; here it leads the tool bar that is already there.
  const balance = el('span', { class: 'canvas-credits', title: 'Credits pay for generations. An admin can add more.' });
  const drawBalance = () => balance.replaceChildren(creditMark(''), el('b', {}, Number(store.user.credits ?? 0).toLocaleString()), Number(store.user.credits) === 1 ? ' credit' : ' credits');
  drawBalance();
  const leaveBalance = subscribe((change) => { if (change === 'credits') drawBalance(); });
  const dock = quickActions({
    pick: (onPick) => pickFromCanvas(onPick),   // "From canvas" in a reference slot's + menu
    startFrom: () => (selected.size === 1 ? items.find((i) => selected.has(i.id) && i.kind !== 'audio') : null),   // a sound is not a frame to start on
    projectId: () => project || null,
  });

  const agent = agentTabs({
    projectId: () => project,
    // What is selected on the canvas: offered to the message as one suggestion, and read when a message says "this".
    selection: () => items.filter((i) => selected.has(i.id)),
    items: () => items,   // the project's frames, for "@name" in the message
    pickCanvas: (onPick) => pickFromCanvas(onPick),   // "Select from canvas" in the + menu
    onUploaded: () => loadItems().then(draw),   // a file uploaded from the + menu joins the canvas
    onJobs: (ids) => { agentJobs = new Set(ids); for (const [id, frame] of jobFrames) frame.node.classList.toggle('by-agent', agentJobs.has(id)); },
    onMemory: () => showPanel(true, 'kit'),
    onFocus: (id) => focusItem(id),   // a result in the conversation shows that clip on the canvas
    locate: (id) => locate(id),
    onFull: (on) => view.classList.toggle('agent-full', on),   // the agent over the whole canvas
  });
  // The kit: everything the project is made from, by name; its always-on entries go into every shot (what the cast was).
  const shared = kitPanel({
    projectId: () => project,
    selected: () => (selected.size === 1 ? items.find((i) => selected.has(i.id)) || null : null),
    onChange: () => dock.recast(),
  });
  // The panel is open every time the canvas is entered, and remembers which of its two tabs was showing.
  const savedTab = localStorage.getItem('scene.panel.tab');   // Quick actions unless the agent or the memory was chosen
  let tab = savedTab === 'agent' ? 'agent' : savedTab === 'kit' || savedTab === 'memory' ? 'kit'
    : savedTab === 'bulk' && store.user.role === 'admin' ? 'bulk' : 'quick';
  const tabsShown = () => TABS.filter((t) => !t.admin || store.user.role === 'admin');   // Bulk generation is an admin's tool
  const bulk = bulkPanel({ projectId: () => project, onQueued: () => refreshJobs().catch(() => {}) });
  bulk.node.classList.add('hidden');
  const title = el('b', { class: 'panel-title' });
  const tabs = el('div');
  const quick = el('div', { class: 'panel-quick' }, dock.node);
  // The left edge of the panel is a grip: drag it to make the panel wider or narrower, double-click for the usual width.
  let panelWidth = PANEL;
  const setWidth = (width) => {
    panelWidth = clamp(Math.round(width) || PANEL, PANEL_MIN, Math.max(PANEL_MIN, Math.min(PANEL_MAX, (view.clientWidth || 9999) - 280)));
    view.style.setProperty('--panel-w', panelWidth + 'px');
  };
  const keepWidth = () => { localStorage.setItem('scene.panel.width', panelWidth); if (ready) fit(); };
  const grip = el('div', { class: 'panel-grip', title: 'Drag to resize. Double-click for the usual width.', role: 'separator', 'aria-orientation': 'vertical',
    ondblclick: () => { setWidth(PANEL); keepWidth(); },
    onpointerdown: (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      const from = { x: e.clientX, width: panelWidth };
      view.classList.add('resizing');
      track((ev) => setWidth(from.width + from.x - ev.clientX), () => { view.classList.remove('resizing'); keepWidth(); });
    } });
  const panel = el('aside', { class: 'side-panel', 'aria-label': 'Make something' }, grip,
    el('div', { class: 'panel-head' }, title, el('span', { style: 'flex:1' }), tabs,
      el('button', { class: 'icon-btn', title: 'Close (Ctrl or ⌘ + J)', 'aria-label': 'Close the panel', onclick: () => showPanel(false) }, '×')),
    quick, agent.node, shared.node, bulk.node);
  const isOpen = () => view.classList.contains('with-panel');
  const panelButton = el('button', { class: 'btn small quiet', title: 'Show or hide Quick action and the Agent (Ctrl or ⌘ + J)', onclick: () => showPanel(!isOpen()) }, 'Panel');
  function showPanel(open, which = tab) {
    tab = which;
    if (!open || tab !== 'agent') agent.setFull(false);   // full screen is the agent's; closing or leaving it ends it
    view.classList.toggle('with-panel', open);
    panelButton.setAttribute('aria-pressed', String(open));
    localStorage.setItem('scene.panel.tab', tab);
    title.textContent = TABS.find((t) => t.id === tab).label;
    title.classList.toggle('agent-name', tab === 'agent');
    tabs.replaceChildren(segmented(tabsShown().map((t) => ({ id: t.id, label: icon(t.icon), hint: t.label })), tab, (id) => showPanel(true, id)));
    quick.classList.toggle('hidden', tab !== 'quick');
    agent.node.classList.toggle('hidden', tab !== 'agent');
    shared.node.classList.toggle('hidden', tab !== 'kit');
    bulk.node.classList.toggle('hidden', tab !== 'bulk');
    if (open && tab === 'bulk') bulk.draw();
    if (open && tab === 'kit') shared.load();   // what the agent has just made or kept shows at once
    if (open) (tab === 'agent' ? agent : tab === 'kit' ? shared : tab === 'bulk' ? bulk : dock).focus();
    if (ready) fit();
  }

  // ------------------------------------------------------------ asset boards

  // People in the project: add them by email with a role, from the canvas as from the project's page.
  const shareButton = el('button', { class: 'btn small quiet hidden', title: 'People in this project', 'aria-label': 'People in this project',
    onclick: () => { const here = projects.find((p) => p.id === project); if (here) shareDialog({ projectId: here.parent_id || here.id, projectName: here.parent_name || here.name }); } },
    icon('people'), 'Share');
  // ------------------------------------------------------------ tools: bring files in, and take work from the library

  const toolNote = el('div', { class: 'float canvas-tool-note hidden', role: 'status', 'aria-live': 'polite' });
  let noteTimer = null;
  const note = (text, { error = false, stay = false } = {}) => {
    clearTimeout(noteTimer);
    toolNote.textContent = text;
    toolNote.classList.toggle('error', error);
    toolNote.classList.toggle('hidden', !text);
    if (!stay) noteTimer = setTimeout(() => toolNote.classList.add('hidden'), error ? 6000 : 2500);
  };
  const filePicker = el('input', { type: 'file', accept: 'image/*,video/*,audio/*,.heic,.heif,.avif,.docx,.pdf,.txt,.md,.srt,.json', multiple: true, hidden: true,
    onchange: (e) => { uploadFiles([...e.target.files]); e.target.value = ''; } });
  // Each file joins the library and this project, and lands on the canvas as a shot of its own.
  async function uploadFiles(files) {
    const usable = files.filter((f) => /^(image|video|audio)\//.test(f.type));
    if (!usable.length) return note('Only images, videos and sound can be uploaded.', { error: true });
    const made = [];
    for (const [i, file] of usable.entries()) {
      note(usable.length > 1 ? `Uploading ${i + 1} of ${usable.length}: ${file.name}` : `Uploading ${file.name}…`, { stay: true });
      const data = new FormData();
      data.append('file', file, file.name);
      data.append('project_id', project || '');
      try { made.push((await api('/api/library/upload', { method: 'POST', body: data })).id); } catch (e) { return note(e.message, { error: true }); }
    }
    await loadItems();
    selected.clear();
    for (const id of made) selected.add(id);
    draw();
    note(made.length === 1 ? 'Uploaded. It is on the canvas.' : `${made.length} files uploaded. They are on the canvas.`);
  }
  stage.addEventListener('dragover', (e) => { if ([...e.dataTransfer.types].includes('Files')) { e.preventDefault(); view.classList.add('dropping'); } });
  stage.addEventListener('dragleave', (e) => { if (e.target === stage) view.classList.remove('dropping'); });
  stage.addEventListener('drop', (e) => {
    if (!e.dataTransfer.files.length) return;
    e.preventDefault();
    view.classList.remove('dropping');
    uploadFiles([...e.dataTransfer.files]);
  });

  // The library drawer: everything the user has made or brought in, to bring onto this canvas.
  const drawer = el('div', { class: 'float canvas-library hidden', role: 'dialog', 'aria-label': 'Library' });
  const shelf = { kind: '', q: '', all: [], loaded: false };
  const libraryButton = el('button', { type: 'button', class: 'tool-btn', 'aria-label': 'Library', 'data-tip': 'Library', onclick: () => toggleLibrary() }, icon('grid'));
  async function toggleLibrary(open = drawer.classList.contains('hidden')) {
    drawer.classList.toggle('hidden', !open);
    libraryButton.classList.toggle('on', open);
    if (!open) return;
    drawShelf();
    try { shelf.all = (await api('/api/library')).items; shelf.loaded = true; } catch (e) { return note(e.message, { error: true }); }
    drawShelf();
  }
  const grid = el('div', { class: 'library-grid' });
  const kinds = el('div');
  drawer.append(
    el('div', { class: 'library-head' }, el('b', {}, 'Library'), el('span', { style: 'flex:1' }),
      el('a', { class: 'btn small quiet', href: '/library' }, 'Open page'),
      el('button', { class: 'icon-btn', 'aria-label': 'Close the library', title: 'Close', onclick: () => toggleLibrary(false) }, '×')),
    kinds,
    el('input', { type: 'search', class: 'search', placeholder: 'Search by name', 'aria-label': 'Search the library',
      oninput: (e) => { shelf.q = e.target.value; drawShelf(); } }),
    grid);
  function drawShelf() {
    kinds.replaceChildren(segmented([{ id: '', label: 'All' }, { id: 'image', label: 'Images' }, { id: 'video', label: 'Videos' }, { id: 'audio', label: 'Audio' }],
      shelf.kind, (k) => { shelf.kind = k; drawShelf(); }));
    const words = shelf.q.toLowerCase().split(/\s+/).filter(Boolean);
    const shown = shelf.all.filter((i) => (!shelf.kind || i.kind === shelf.kind) && words.every((w) => i.name.toLowerCase().includes(w)));
    grid.replaceChildren(...(shown.length ? shown.map((item) => {
      const here = !project || item.project_id === project;
      return el('button', { type: 'button', class: 'library-tile' + (here ? ' here' : ''),
        title: here ? 'Open it' : `In ${item.project_name || 'no project'}. Click to move it to this project's canvas.`,
        onclick: async () => {
          if (here) return open(item);
          try {
            await api('/api/library/' + item.id, { method: 'PUT', json: { project_id: project } });
            item.project_id = project;
            await loadItems();
            selected.clear();
            selected.add(item.id);
            draw();
            drawShelf();
            note(`${item.name} is on the canvas.`);
          } catch (e) { note(e.message, { error: true }); }
        } },
        el('span', { class: 'library-thumb' }, still(`/api/library/${item.id}/file`, item.kind, item.name)),
        el('span', { class: 'library-name' }, item.name),
        el('span', { class: 'library-where' }, here ? (project ? 'On this canvas' : item.project_name || 'No project') : '+ Add to canvas'));
    }) : [el('p', { class: 'muted small' }, shelf.loaded ? (shelf.all.length ? 'Nothing matches.' : 'Your library is empty.') : 'Loading…')]));
  }
  const tools = el('div', { class: 'float canvas-tools', role: 'toolbar', 'aria-label': 'Canvas tools', 'aria-orientation': 'vertical' },
    el('button', { type: 'button', class: 'tool-btn', 'aria-label': 'Upload an image, video or sound', 'data-tip': 'Upload image, video or audio',
      onclick: () => filePicker.click() }, icon('upload')),
    libraryButton, filePicker);

  view.replaceChildren(stage,
    el('div', { class: 'float canvas-bar' }, picker, count, shareButton, timelineLink),
    tools, drawer, toolNote,
    context,
    el('div', { class: 'float canvas-view' },
      balance,
      el('button', { class: 'btn small quiet canvas-zoom', title: 'Fit everything (1)', onclick: () => fit(true) }, 'Fit'),
      zoomLabel, panelButton),
    map, hint, panel);

  // ------------------------------------------------------------ layout

  const lazy = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      lazy.unobserve(entry.target);
      entry.target.append(media(entry.target.item));
    }
  }, { root: stage, rootMargin: '300px' });

  const media = (item) => still(`/api/library/${item.id}/file`, item.kind, item.name);

  // Every shot is a row. Work made from scratch starts a new row at the bottom; work made from a frame
  // (continued from it, re-run, trimmed, split) joins that frame's row at the right end.
  const rowOf = (key) => layout.rows.find((row) => row.keys.includes(key));
  const newRow = () => layout.rows[layout.rows.push({ id: ++layout.count, name: '', keys: [] }) - 1];
  // The frame something was made from: sent with the job, or the first clip of an edit.
  const parentOf = (settings) => (settings && (settings.parent || (Array.isArray(settings.clips) && settings.clips[0] && settings.clips[0].id))) || null;
  // The row of a numbered shot, made when its first take comes.
  const shotRow = (n) => layout.rows.find((row) => row.shot === n) || Object.assign(newRow(), { shot: n });
  // What a row is called: the name given to it, its shot number, or, for a row with no number, the next numbers after
  // the highest one, so two rows are never both called "Shot 3".
  function rowName(row, plain = false) {
    if (row.name && !plain) return row.name;
    if (row.shot) return `Shot ${row.shot}`;
    const top = Math.max(0, ...layout.rows.filter((r) => r.shot).map((r) => r.shot));
    return `Shot ${top + layout.rows.filter((r) => !r.shot).indexOf(row) + 1}`;
  }
  // The board a name given by a job goes on: one of the usual boards by its label ("Characters"), or a board of its own.
  const boardOf = (name) => { const known = BOARDS.find(([, label]) => label.toLowerCase() === String(name).toLowerCase()); return known ? known[0] : 'named:' + name; };
  const boardList = () => [...BOARDS, ...placed.boards.filter((b) => boardOf(b.name).startsWith('named:')).map((b) => ['named:' + b.name, b.name])];
  // A stack's members, newest first, put in the order they are drawn: the one on top first. The newest is on top unless
  // the user switched to another take since the last one came.
  function stacked(key, members) {
    const pick = layout.picks[key];
    const top = pick && pick.count === members.length && members.includes(pick.key) ? pick.key : members[0];
    return [top, ...members.filter((k) => k !== top)];
  }
  // Spots for a stack whose top is at (x, y): earlier takes behind it, each a little up and to the right.
  function stackSpots(stack, order, x, y, sizes, extra = {}) {
    order.forEach((key, depth) => {
      const takeNo = stack.members.length - stack.members.indexOf(key);   // the oldest is take 1
      const shown = Math.min(depth, STACK_SHOWN);
      spots.set(key, { x: x + shown * STACK_STEP, y: y - shown * STACK_STEP, h: sizes(key), depth, stack, takeNo,
        label: stack.shot ? `Take ${takeNo} of ${stack.members.length}` : '', ...extra });
    });
  }

  function arrange() {
    const before = JSON.stringify(layout);
    const jobs = store.jobs.filter((j) => (ACTIVE.includes(j.status) || (j.status === 'failed' && j.finished && Date.now() / 1000 - j.finished < FAILED_SHOWN))
      && (!project || j.project_id === project));
    const known = new Set(items.map((i) => i.id));
    // A job that has just finished keeps its place until what it made comes in (a moment later), so the result lands
    // where the job was and the shots never trade places. Two minutes at most: a job may make nothing to show here.
    const landing = store.jobs.filter((j) => j.status === 'done' && (!project || j.project_id === project) && j.finished
      && Date.now() / 1000 - j.finished < 120 && !items.some((i) => i.job_id === j.id));
    const live = new Set([...jobs, ...landing].map((j) => 'job:' + j.id));
    onBoard.clear();
    for (const e of kitEntries) if (e.item && known.has(e.item)) onBoard.set(e.item, { board: e.tag in BOARD_LABEL ? e.tag : 'other', name: e.name });
    for (const item of items) if (item.workflow === FINAL_CUT && !onBoard.has(item.id)) onBoard.set(item.id, { board: 'outputs', name: item.name });
    // A result its job put on a named board ("Characters", "Outputs") sits there, on the stack of what it is a version of.
    const named = new Map(items.map((i) => [i.id, i]));
    for (const board of placed.boards) {
      for (const s of board.stacks || []) {
        const members = (s.items || []).filter((id) => known.has(id));
        if (!members.length) continue;
        const stack = { key: `board:${board.name}:${s.group}`, members };
        for (const id of members) onBoard.set(id, { board: boardOf(board.name), name: named.get(id).name, stack });
      }
    }
    for (const item of [...items].reverse()) {   // oldest first, so shots are numbered in the order they were made
      if (onBoard.has(item.id)) continue;
      const n = shotNumber(item.settings);
      if (n) {   // a numbered shot is always in its own row, wherever it was dragged
        const row = shotRow(n);
        if (!row.keys.includes(item.id)) {
          for (const other of layout.rows) other.keys = other.keys.filter((key) => key !== item.id);
          row.keys.push(item.id);
        }
        continue;
      }
      if (rowOf(item.id)) continue;
      const held = item.job_id && rowOf('job:' + item.job_id);   // finished work takes the place its job was holding
      if (held) held.keys.splice(held.keys.indexOf('job:' + item.job_id), 0, item.id);
      else (rowOf(parentOf(item.settings)) || newRow()).keys.push(item.id);
    }
    for (const job of [...jobs].reverse()) {
      if (rowOf('job:' + job.id) || items.some((i) => i.job_id === job.id)) continue;
      const n = shotNumber(job.settings);
      (n ? shotRow(n) : rowOf(parentOf(job.settings)) || newRow()).keys.push('job:' + job.id);
    }
    for (const row of layout.rows) row.keys = row.keys.filter((key) => (typeof key === 'number' ? known.has(key) && !onBoard.has(key) : live.has(key)));
    layout.rows = layout.rows.filter((row) => row.keys.length);
    // Numbered shots first, in the order of their numbers; the other rows after them, as they were.
    layout.rows = [...layout.rows.filter((row) => row.shot).sort((a, b) => a.shot - b.shot), ...layout.rows.filter((row) => !row.shot)];
    for (const key of Object.keys(layout.picks)) if (!layout.rows.some((row) => `shot:${row.shot}` === key) && !key.startsWith('board:')) delete layout.picks[key];

    const heights = new Map(items.map((i) => [i.id, heightOf(i)]));
    const jobOf = new Map(store.jobs.map((j) => ['job:' + j.id, j]));
    const settingsOf = (key) => (typeof key === 'number' ? (named.get(key) || {}).settings : (jobOf.get(key) || {}).settings);
    const madeAt = (key) => (typeof key === 'number' ? (named.get(key) || {}).created : (jobOf.get(key) || {}).created) || 0;
    const sizeOf = (key) => heights.get(key) || heightOf();
    spots.clear();
    bands = [];
    let y = 0;
    for (const row of layout.rows) {
      const sizes = row.keys.map(sizeOf);
      // A numbered row's takes of its shot are one stack at the left, the newest on top; the rest of the row (work made
      // from them: a trim, an upscale) follows it.
      const members = row.shot ? row.keys.filter((key) => shotNumber(settingsOf(key)) === row.shot).sort((a, b) => madeAt(b) - madeAt(a)) : [];
      const rest = row.keys.filter((key) => !members.includes(key));
      if (members.length) stackSpots({ key: `shot:${row.shot}`, members, shot: row.shot }, stacked(`shot:${row.shot}`, members), 0, y, sizeOf);
      rest.forEach((key, i) => spots.set(key, { x: (i + (members.length ? 1 : 0)) * (FRAME + GAP), y, h: sizeOf(key) }));
      bands.push({ row, y, h: Math.max(...sizes) });
      y += Math.max(...sizes) + SLATE + GAP;
    }
    placeBoards(heights);
    if (ready && JSON.stringify(layout) !== before) save();
    return jobs;
  }

  // The boards, side by side left of the names of the shots, their tops level with the first shot. Each holds its
  // entries two to a row: the name of the entry above its frame.
  function placeBoards(heights) {
    const boards = boardList();
    const groups = new Map(boards.map(([id]) => [id, []]));
    for (const item of items) {
      const where = onBoard.get(item.id);
      if (!where) continue;
      // A stack is one card: its top take, with the others behind it.
      const order = where.stack && where.stack.members.length > 1 ? stacked(where.stack.key, where.stack.members) : null;
      if (order && order[0] !== item.id) continue;
      // The takes behind peek out above it: the card is that much taller, so they stay clear of the entry's name.
      const lift = order ? Math.min(order.length - 1, STACK_SHOWN) * STACK_STEP : 0;
      (groups.get(where.board) || groups.get('other')).push({ key: item.id, name: where.name, h: (heights.get(item.id) || heightOf()) + lift, lift, stack: order && where.stack, order });
    }
    for (const e of kitEntries) {
      if (e.item && onBoard.has(e.item)) continue;   // shown by its library item
      const board = e.tag in BOARD_LABEL ? e.tag : 'other';
      groups.get(board).push({ key: 'kit:' + e.id, name: e.name, h: e.kind === 'image' ? Math.round(FRAME * 0.75) : 96, entry: e });
    }
    const used = boards.filter(([id]) => groups.get(id).length);
    const sizes = used.map(([id, label]) => {
      const entries = groups.get(id);
      const cols = entries.length > 1 ? 2 : 1;
      const rows = [];
      for (let i = 0; i < entries.length; i += cols) rows.push(entries.slice(i, i + cols));
      const w = BOARD_PAD * 2 + cols * FRAME + (cols - 1) * GAP / 2;
      const h = BOARD_HEAD + BOARD_PAD + rows.reduce((sum, row) => sum + ENTRY_NAME + Math.max(...row.map((e) => e.h)) + SLATE + GAP / 2, 0);
      return { id, label, entries, rows, w, h };
    });
    const total = sizes.reduce((sum, s) => sum + s.w + GAP, 0);
    let x = -LABEL - GAP - total;
    const top = bands.length ? bands[0].y - GAP / 3 : 0;
    boardCards = [];
    for (const s of sizes) {
      const card = { label: s.label, count: s.entries.length, x, y: top, w: s.w, h: s.h, names: [] };
      let y = top + BOARD_HEAD;
      for (const row of s.rows) {
        row.forEach((e, i) => {
          const ex = x + BOARD_PAD + i * (FRAME + GAP / 2);
          card.names.push({ text: e.name, x: ex, y });
          if (e.order) stackSpots(e.stack, e.order, ex, y + ENTRY_NAME + e.lift, (key) => heights.get(key) || heightOf(), { board: true });
          else spots.set(e.key, { x: ex, y: y + ENTRY_NAME, h: e.h, board: true, entry: e.entry });
        });
        y += ENTRY_NAME + Math.max(...row.map((e) => e.h)) + SLATE + GAP / 2;
      }
      boardCards.push(card);
      x += s.w + GAP;
    }
  }

  function drawItems() {
    for (const key of [...boxes.keys()]) if (typeof key === 'number') boxes.delete(key);
    lazy.disconnect();
    itemLayer.replaceChildren(...items.map((item) => {
      const spot = spots.get(item.id);
      const shot = el('div', { class: 'shot gate', style: `height:${spot.h}px` });
      shot.item = item;
      lazy.observe(shot);
      const c = item.context || {};
      const label = el('b', {}, spot.board ? (onBoard.get(item.id) || {}).name || item.name : take(spot));
      // "+" on a frame adds it to the agent's message, opening the agent when it is not showing.
      const toChat = el('button', { type: 'button', class: 'frame-attach', title: 'Add to chat', 'aria-label': `Add ${item.name} to the chat`,
        onpointerdown: (e) => e.stopPropagation(), ondblclick: (e) => e.stopPropagation(),
        onclick: (e) => { e.stopPropagation(); addToChat([item]); } }, icon('plus'));
      const n = shotNumber(item.settings);
      const depth = spot.depth || 0;
      const node = el('div', { class: 'frame' + (selected.has(item.id) ? ' selected' : ''), style: `left:${spot.x}px;top:${spot.y}px` + (spot.stack ? `;z-index:${STACK_SHOWN + 1 - Math.min(depth, STACK_SHOWN)}` : ''),
        title: depth ? `${item.name}: an earlier take. Click to put it on top.` : item.name,
        onpointerdown: (e) => grab(e, item.id), ondblclick: () => open(item) },
        shot, toChat,
        n && el('span', { class: 'shot-badge', title: `Shot ${n} of the story` }, `Shot ${n}`),
        !depth && spot.stack && spot.stack.members.length > 1 && takeSwitch(spot.stack, item.id),
        el('div', { class: 'slate' }, label, el('span', {}, c.width ? `${item.kind} · ${c.width}×${c.height}` : item.name)));
      if (depth) node.classList.add('stack-behind');
      if (depth > STACK_SHOWN) node.classList.add('stack-buried');
      if (spot.board) node.classList.add('on-board');
      else node.take = label;
      boxes.set(item.id, { key: item.id, ...spot, node });
      return node;
    }));
    drawFiles();
    count.textContent = items.length === 1 ? '1 item' : `${items.length} items`;
  }

  // Put one take of a stack on top. It stays there until the user switches again or a new take comes.
  function pickTake(stack, key) {
    layout.picks[stack.key] = { key, count: stack.members.length };
    draw();
    save();
  }
  // "‹ 2 / 3 ›" on the take on top of a stack: the earlier take, which one this is, the later take. Takes count from
  // the oldest, so the newest has the highest number.
  function takeSwitch(stack, key) {
    const index = stack.members.indexOf(key);   // members are newest first
    const total = stack.members.length;
    const step = (by) => (e) => { e.stopPropagation(); pickTake(stack, stack.members[(index + by + total) % total]); };
    const button = (text, by, hint) => el('button', { type: 'button', class: 'stack-step', title: hint, 'aria-label': hint,
      onpointerdown: (e) => e.stopPropagation(), ondblclick: (e) => e.stopPropagation(), onclick: step(by) }, text);
    return el('div', { class: 'stack-switch', role: 'group', 'aria-label': 'Takes of this shot' },
      button('‹', 1, 'The earlier take'), el('span', {}, `${total - index} / ${total}`), button('›', -1, 'The later take'));
  }

  // NeuralCore entries that are files of their own (uploaded, or kept from a reference): a frame on their board. A
  // double click opens the file.
  function drawFiles() {
    for (const key of [...boxes.keys()]) if (String(key).startsWith('kit:')) boxes.delete(key);
    fileLayer.replaceChildren(...[...spots.entries()].filter(([key]) => String(key).startsWith('kit:')).map(([key, spot]) => {
      const e = spot.entry;
      const node = el('div', { class: 'frame on-board file-frame', style: `left:${spot.x}px;top:${spot.y}px`, title: `${e.name} (NeuralCore)`,
        ondblclick: () => window.open(e.url, '_blank', 'noopener') },
        // A picture shows itself; a clip, a sound or a script shows what it is (a NeuralCore file has no poster).
        el('div', { class: 'shot', style: `height:${spot.h}px` }, e.kind === 'image' ? still(e.url, 'image', e.name)
          : el('div', { class: 'sound' }, icon(e.kind === 'video' ? 'video' : e.kind === 'audio' ? 'audio' : 'book'), el('span', {}, e.name))),
        el('div', { class: 'slate' }, el('b', {}, e.name), el('span', {}, e.type || '')));
      boxes.set(key, { key, ...spot, node });
      return node;
    }));
  }

  // A job that failed: what it was, why in plain words, and that its credits came back. It stays a day, then goes.
  function failedFrame(job, spot) {
    const shot = el('div', { class: 'shot failed-shot', style: `height:${spot.h}px` },
      el('b', {}, "Didn't work"),
      el('span', {}, job.reason || 'Something went wrong while it was being made.'),
      el('span', { class: 'failed-credits' }, job.cost ? `Your ${job.cost} credits came back.` : ''));
    const node = el('div', { class: 'frame failed', title: 'Open for the details', role: 'button', tabindex: '0',
      onclick: () => failedDetails(job), onkeydown: (e) => { if (e.key === 'Enter') failedDetails(job); } },
      shot, el('div', { class: 'slate' }, el('b', {}, job.workflow.split('/')[0]), el('span', {}, job.name)));
    return { node, failed: true };
  }

  // What a failed job was asked to make and what became of it, opened from its frame. An admin also sees the render
  // server's own words, for working out what went wrong.
  function failedDetails(job) {
    const s = job.settings || {};
    const when = (t) => (t ? new Date(t * 1000).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '');
    const ran = job.started && job.finished ? Math.max(0, Math.round(job.finished - job.started)) : null;
    const chosen = [s.resolution && `${s.resolution}p`, s.orientation, ...Object.entries(s.options || {}).map(([k, v]) => `${k}: ${v}`)].filter(Boolean).join(' · ');
    const facts = [['Model', s.workflow_title || job.workflow], ['Prompt', s.prompt], ['Settings', chosen || job.summary],
      ['Asked at', when(job.created)], ['Stopped at', when(job.finished)],
      ['Ran for', ran == null ? '' : ran < 90 ? `${ran} s` : `${Math.round(ran / 60)} min`],
      ['Credits', job.cost ? `${job.cost} charged, all ${job.cost} given back` : 'Free']].filter(([, v]) => v);
    const dialog = el('dialog', { class: 'failed-dialog', 'aria-label': 'Why it didn\'t work' },
      el('h2', {}, "Didn't work"),
      el('p', { class: 'failed-reason' }, job.reason || 'Something went wrong while it was being made.'),
      el('dl', { class: 'failed-facts' }, facts.flatMap(([k, v]) => [el('dt', {}, k), el('dd', {}, v)])),
      store.user.role === 'admin' && job.error && el('details', { class: 'failed-raw' }, el('summary', {}, 'What the render server said'), el('pre', {}, job.error)),
      el('div', { class: 'row', style: 'justify-content:flex-end;margin-top:16px' },
        el('button', { class: 'btn', onclick: () => dialog.close() }, 'Close')));
    dialog.addEventListener('close', () => dialog.remove());
    document.body.append(dialog);
    dialog.showModal();
  }

  // Frames of jobs are kept between updates, so the running Gate isn't restarted by every progress message.
  function drawJobs(jobs) {
    for (const [id, frame] of jobFrames) {
      if (jobs.some((j) => j.id === id)) continue;
      frame.node.remove();
      jobFrames.delete(id);
      boxes.delete('job:' + id);
    }
    for (const job of jobs) {
      const spot = spots.get('job:' + job.id);
      if (!spot) continue;   // its result is already on the canvas
      let frame = jobFrames.get(job.id);
      // It was running and has just failed: drawn anew. Only then: a running frame is kept between updates, so what moves
      // on it is never restarted by a progress message.
      if (frame && !frame.failed && job.status === 'failed') {
        frame.node.remove();
        jobFrames.delete(job.id);
        frame = null;
      }
      if (!frame && job.status === 'failed') {
        frame = failedFrame(job, spot);
        jobFrames.set(job.id, frame);
        jobLayer.append(frame.node);
        boxes.set('job:' + job.id, { key: 'job:' + job.id, ...spot, node: frame.node });
      }
      if (frame && frame.failed) continue;
      if (!frame) {
        const clock = el('span');
        const fact = el('span');
        // Under the clock, a paper plane or a clapperboard, looping on its own (it does not follow the job's steps), one or
        // the other at random. The pick comes from the job's id, so a frame keeps its own while it is redrawn.
        const film = [...job.id].reduce((n, c) => n + c.charCodeAt(0), 0) % 2 ? clapper() : flight();
        const progress = reel(32);   // under the frame, as wide as it: a reel of film that fills in with the job's steps
        const shot = el('div', { class: 'shot', style: `height:${spot.h}px` }, el('div', { class: 'shot-wait' }, clock, film.node));
        const node = el('div', { class: 'frame developing' + (agentJobs.has(job.id) ? ' by-agent' : ''), title: job.name },
          shot, progress.node, el('div', { class: 'slate' }, el('b', {}, job.workflow.split('/')[0]), fact));
        frame = { node, shot, clock, fact, film, progress, gate: null };
        jobFrames.set(job.id, frame);
        jobLayer.append(node);
        boxes.set('job:' + job.id, { key: 'job:' + job.id, ...spot, node });
      }
      const waiting = job.status === 'queued';
      if (!waiting && !frame.gate) frame.gate = frame.shot.appendChild(runningGate());
      // The frame develops like a print in a tray: the grain clears as the steps go by.
      const done = job.steps ? (Math.max(job.clip, 1) - 1 + job.step / job.steps) / Math.max(job.clips, 1) : 0;
      frame.shot.style.setProperty('--developed', done.toFixed(3));
      frame.progress.set(done);
      frame.node.classList.toggle('waiting', waiting);
      frame.clock.textContent = waiting ? 'queued' : elapsed(job);   // how long it has been at it; no percentage
      // Words only while it waits (its place in the queue); while it runs, the clock and the animation are enough.
      frame.fact.textContent = waiting ? (job.waiting_for_server ? 'waiting for the render server' : `position ${job.position}`) : '';
    }
    hint.classList.toggle('hidden', boxes.size > 0);
  }

  // Move every frame to where its row puts it, and name the rows down the left side.
  function settle() {
    for (const box of boxes.values()) {
      const spot = spots.get(box.key);
      if (!spot) continue;
      Object.assign(box, spot);
      box.node.style.left = spot.x + 'px';
      box.node.style.top = spot.y + 'px';
      // On a stack the take on top is drawn over the ones behind it (a running retake too).
      box.node.style.zIndex = spot.stack ? String(STACK_SHOWN + 1 - Math.min(spot.depth || 0, STACK_SHOWN)) : '';
      if (box.node.take) box.node.take.textContent = take(spot);
    }
    // All the shots sit in one board, the names of the shots down its left side and a line between one shot and the
    // next, halfway across the gap. The board is as wide as the longest shot.
    const pad = GAP / 3;
    const last = bands[bands.length - 1];
    const left = -LABEL - GAP / 4;
    const width = Math.max(1, ...bands.map((band) => band.row.keys.length)) * (FRAME + GAP) - left - GAP / 2;
    boardBox = { left, width };
    const board = last ? [el('div', { class: 'lane lane-board',
      style: `left:${left}px;top:${bands[0].y - pad}px;width:${width}px;height:${last.y + last.h + SLATE + pad - (bands[0].y - pad)}px` })] : [];
    const lines = bands.slice(1).map((band, i) => {
      const above = bands[i];
      const y = (above.y + above.h + SLATE + band.y) / 2;
      return el('div', { class: 'lane-divider', style: `left:${left + GAP / 4}px;top:${y}px;width:${width - GAP / 2}px` });
    });
    const cards = boardCards.flatMap((c) => [
      el('div', { class: 'board-card', style: `left:${c.x}px;top:${c.y}px;width:${c.w}px;height:${c.h}px` },
        el('span', { class: 'board-chip' }, icon('grid'), c.label, el('i', {}, String(c.count)))),
      ...c.names.map((n) => el('div', { class: 'board-name', style: `left:${n.x}px;top:${n.y}px;width:${FRAME}px`, title: n.text }, n.text))]);
    labelLayer.replaceChildren(...cards, ...board, ...lines,
    ...bands.map((band, i) => el('button', { class: 'shot-label', title: 'Rename this shot',
      style: `left:${-LABEL}px;top:${band.y}px;width:${LABEL - GAP / 2}px;height:${band.h}px`,
      onpointerdown: (e) => e.stopPropagation(), onclick: (e) => rename(band.row, e.currentTarget, i) }, rowName(band.row))));
    drawOverlay();
  }

  function rename(row, label, index) {
    const input = el('input', { type: 'text', class: 'shot-name', maxlength: 40, value: rowName(row), 'aria-label': 'Name of the shot' });
    const done = (keep) => {
      if (!input.isConnected) return;
      if (keep) { row.name = input.value.trim() === rowName(row, true) ? '' : input.value.trim(); save(); }
      settle();
    };
    input.addEventListener('pointerdown', (e) => e.stopPropagation());
    input.addEventListener('blur', () => done(true));
    input.addEventListener('keydown', (e) => { e.stopPropagation(); if (e.key === 'Enter') done(true); else if (e.key === 'Escape') done(false); });
    label.replaceChildren(input);
    input.select();
  }

  // update(): jobs or rows changed. draw(): the items themselves changed, so their frames are rebuilt too.
  function update() {
    const jobs = arrange();
    drawJobs(jobs);
    settle();
  }

  function draw() {
    const jobs = arrange();
    drawItems();
    drawJobs(jobs);
    settle();
  }

  // ------------------------------------------------------------ one item in view: where the agent's results lead

  // Where an item is, as the agent's panel names it: "Shot 3", take 2.
  function locate(id) {
    const index = layout.rows.findIndex((row) => row.keys.includes(id));
    if (index < 0) return null;
    const row = layout.rows[index];
    return { shot: rowName(row), take: (spots.get(id) || {}).takeNo || row.keys.indexOf(id) + 1 };
  }

  // Glide to one item and select it: it comes to the middle of the part of the canvas the panel leaves free, at a size
  // it can be seen at, with a ring that shows which one it is.
  async function focusItem(id) {
    if (!boxes.has(id)) {   // made a moment ago, it may not be drawn yet
      try { await loadItems(); draw(); } catch { /* said below */ }
    }
    const box = boxes.get(id);
    if (!box) return note(project ? 'That one is not in this project. Pick All work to see it.' : 'That one is no longer in the library.', { error: true });
    const rect = stage.getBoundingClientRect();
    const covered = isOpen() ? panelWidth + 12 : 0;
    const room = { w: Math.max(200, rect.width - covered), h: rect.height };
    const k = clamp(Math.min((room.w * 0.55) / FRAME, (room.h * 0.62) / (box.h + SLATE)), 0.35, 1.6);
    glideTo({ k, x: room.w / 2 - (box.x + FRAME / 2) * k, y: room.h / 2 - (box.y + (box.h + SLATE) / 2) * k });
    selected.clear();
    selected.add(id);
    selectionChanged();
    box.node.classList.remove('spotlight');
    void box.node.offsetWidth;   // starts the ring again when it is already there
    box.node.classList.add('spotlight');
  }

  // ------------------------------------------------------------ camera

  // The camera moves on springs: a flicked board carries on and settles, and Fit or a result picked in the conversation
  // glides there. Touching the board, the wheel or a zoom catches it where it is.
  let moves = [];
  function stopCamera() { moves.forEach((spring) => spring.stop()); moves = []; }
  function glideTo(to) {
    stopCamera();
    const from = { ...cam };
    moves = [new Spring(0, (p) => {
      cam.x = from.x + (to.x - from.x) * p;
      cam.y = from.y + (to.y - from.y) * p;
      cam.k = from.k + (to.k - from.k) * p;
      applyCamera();
    }, 0.001).to(1, { response: 0.5 })];
  }

  // How far the board can be pushed: some of the work always stays in sight, so it is never lost off an edge.
  function limits() {
    if (!boxes.size) return null;
    const all = bounds([...boxes.values()]);
    const rect = stage.getBoundingClientRect();
    const keep = 160;
    return { minX: keep - all.right * cam.k, maxX: rect.width - keep - (all.x - LABEL) * cam.k, w: rect.width,
      minY: keep - all.bottom * cam.k, maxY: rect.height - keep - all.y * cam.k, h: rect.height };
  }
  // Past a limit the board follows the pointer less and less.
  const soft = (raw, low, high, size) => (raw < low ? low - rubberband(low - raw, size) : raw > high ? high + rubberband(raw - high, size) : raw);

  // A drag let go: the board carries on at the pointer's speed and settles inside its limits.
  function throwCamera(velocity) {
    stopCamera();
    const edge = limits();
    if (!edge) return;
    const axis = (key, speed, low, high) => {
      const out = cam[key] < low || cam[key] > high;
      return new Spring(cam[key], (value) => { cam[key] = value; applyCamera(); })
        .to(clamp(cam[key] + carry(speed), low, high), { response: out ? 0.45 : 0.8, velocity: speed });
    };
    moves = [axis('x', velocity.x, edge.minX, edge.maxX), axis('y', velocity.y, edge.minY, edge.maxY)];
  }

  function applyCamera() {
    world.style.transform = `translate(${cam.x}px, ${cam.y}px) scale(${cam.k})`;
    world.style.setProperty('--inv', 1 / cam.k);
    stage.style.setProperty('--grid', 96 * cam.k + 'px');
    stage.style.setProperty('--grid-x', cam.x + 'px');
    stage.style.setProperty('--grid-y', cam.y + 'px');
    stage.classList.toggle('far', cam.k < 0.5);   // far away: just the pictures, no slates or grid
    zoomLabel.textContent = Math.round(cam.k * 100) + '%';
    drawOverlay();
  }

  function zoomAt(clientX, clientY, k) {
    stopCamera();
    const rect = stage.getBoundingClientRect();
    const px = clientX - rect.left;
    const py = clientY - rect.top;
    const wx = (px - cam.x) / cam.k;
    const wy = (py - cam.y) / cam.k;
    cam.k = clamp(k, MIN_ZOOM, MAX_ZOOM);
    cam.x = px - wx * cam.k;
    cam.y = py - wy * cam.k;
    applyCamera();
  }

  function zoomTo(k) {
    const rect = stage.getBoundingClientRect();
    zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, k);
  }

  function bounds(list) {
    return { x: Math.min(...list.map((b) => b.x)), y: Math.min(...list.map((b) => b.y)),
      right: Math.max(...list.map((b) => b.x + FRAME)), bottom: Math.max(...list.map((b) => b.y + b.h + SLATE)) };
  }

  // animate: glide there (Fit, the 1 key); otherwise jump, as when the page opens or the panel is resized.
  function fit(animate = false) {
    if (!boxes.size) { stopCamera(); cam.x = 96; cam.y = 96; cam.k = 1; return applyCamera(); }
    const all = bounds([...boxes.values()]);
    all.x -= LABEL;   // the names of the shots are part of the picture
    const rect = stage.getBoundingClientRect();
    const covered = isOpen() ? panelWidth + 12 : 0;   // the open panel covers the right side
    const room = { w: rect.width - 160 - covered, h: rect.height - 160 };
    const k = clamp(Math.min(room.w / (all.right - all.x), room.h / (all.bottom - all.y)), MIN_ZOOM, 1);
    const to = { k, x: (rect.width - covered - (all.right - all.x) * k) / 2 - all.x * k, y: 80 + (room.h - (all.bottom - all.y) * k) / 2 - all.y * k };
    if (animate) return glideTo(to);
    stopCamera();
    Object.assign(cam, to);
    applyCamera();
  }

  stage.addEventListener('wheel', (e) => {
    e.preventDefault();
    stopCamera();
    if (e.ctrlKey || e.metaKey) return zoomAt(e.clientX, e.clientY, cam.k * Math.exp(-e.deltaY * 0.01));
    cam.x -= e.deltaX;
    cam.y -= e.deltaY;
    applyCamera();
  }, { passive: false });

  // Drag the empty canvas to pan; a click on it clears the selection.
  stage.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    stopCamera();
    const from = { x: e.clientX, y: e.clientY, cx: cam.x, cy: cam.y };
    const edge = limits();
    const speed = tracker();
    speed.add(e.clientX, e.clientY);
    let moved = false;
    stage.classList.add('panning');
    track((ev) => {
      speed.add(ev.clientX, ev.clientY);
      moved = moved || Math.abs(ev.clientX - from.x) + Math.abs(ev.clientY - from.y) > 3;
      cam.x = from.cx + ev.clientX - from.x;
      cam.y = from.cy + ev.clientY - from.y;
      if (edge) { cam.x = soft(cam.x, edge.minX, edge.maxX, edge.w); cam.y = soft(cam.y, edge.minY, edge.maxY, edge.h); }
      applyCamera();
    }, () => {
      stage.classList.remove('panning');
      if (moved) throwCamera(speed.velocity());
      else if (selected.size) { selected.clear(); selectionChanged(); }
    });
  });

  function track(onMove, onEnd) {
    const end = () => { window.removeEventListener('pointermove', onMove); window.removeEventListener('pointerup', end); onEnd(); };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', end);
  }

  // ------------------------------------------------------------ selecting and moving

  // Where a dragged frame would start a new shot: in the gap above the first shot or between two shots, near the
  // line between them. The index the new shot takes, or -1 when the pointer is over a shot (it joins that one).
  function gapAt(y) {
    if (!bands.length) return -1;
    if (y > bands[0].y - GAP && y < bands[0].y + 12) return 0;
    for (let i = 1; i < bands.length; i++) {
      if (y > bands[i - 1].y + bands[i - 1].h + SLATE - 12 && y < bands[i].y + 12) return i;
    }
    return -1;
  }
  const gapLine = (i) => (i === 0 ? bands[0].y - GAP / 2 : (bands[i - 1].y + bands[i - 1].h + SLATE + bands[i].y) / 2);
  const insertMark = el('div', { class: 'insert-mark' }, el('span', {}, 'New shot here'));

  // After a drop every frame that changed place slides from where it was to its new spot, so the eye can follow it;
  // the dropped ones land with a little give.
  function settleFrom(was, dropped) {
    for (const [box, at] of was) {
      const dx = at.x - box.x;
      const dy = at.y - box.y;
      if (!box.node.isConnected || (!dx && !dy)) continue;
      new Spring(1, (t) => { box.node.style.translate = t ? `${dx * t}px ${dy * t}px` : ''; }, 0.002)
        .to(0, { response: 0.35, damping: dropped.has(box) ? 0.8 : 1 });
    }
  }

  function grab(e, id) {
    if (e.button !== 0) return;
    e.stopPropagation();
    if (e.shiftKey) { selected.has(id) ? selected.delete(id) : selected.add(id); }
    else if (!selected.has(id)) { selected.clear(); selected.add(id); }
    selectionChanged();
    stopCamera();
    const from = { x: e.clientX, y: e.clientY };
    // What is on a board stays there: it can be selected, opened and added to the chat, not moved into a shot.
    const moving = [...selected].map((key) => boxes.get(key)).filter((box) => box && !box.board).map((box) => ({ box, x: box.x, y: box.y }));
    let moved = false;
    // Where the pointer is on the canvas, to tell a drop on a shot from a drop in the gap between two shots.
    const held = boxes.get(id);
    const grip = held ? (from.y - held.node.getBoundingClientRect().top) / cam.k : 0;
    const startY = held ? held.y + grip : 0;
    let gap = -1;
    track((ev) => {
      const dx = (ev.clientX - from.x) / cam.k;
      const dy = (ev.clientY - from.y) / cam.k;
      moved = moved || Math.abs(dx) + Math.abs(dy) > 3 / cam.k;
      if (!moved || !moving.length) return;
      if (!moving[0].box.node.classList.contains('lifted')) moving.forEach((m) => m.box.node.classList.add('lifted'));
      context.classList.add('hidden');
      gap = gapAt(startY + dy);
      if (gap >= 0) {   // over the line between two shots: it lights up, and the frames will start a new shot there
        Object.assign(insertMark.style, { left: boardBox.left + GAP / 4 + 'px', width: boardBox.width - GAP / 2 + 'px', top: gapLine(gap) + 'px' });
        if (!insertMark.isConnected) labelLayer.append(insertMark);
      } else insertMark.remove();
      for (const m of moving) {
        m.box.x = Math.round((m.x + dx) / SNAP) * SNAP;
        m.box.y = Math.round((m.y + dy) / SNAP) * SNAP;
        m.box.node.style.left = m.box.x + 'px';
        m.box.node.style.top = m.box.y + 'px';
      }
    }, () => {
      // A click only selects: looking at a frame does not put it into the message. The agent offers the selection as
      // one suggestion to use, and each frame has its own "+" to add it. While a panel asked for a frame ("From
      // canvas" with nothing selected), the click gives it this frame.
      if (!moved && picking) { const done = picking; stopPicking(); done(items.find((i) => i.id === id)); return; }
      if (!moved && held && held.depth) return pickTake(held.stack, id);   // an earlier take, clicked: it goes on top
      if (!moved || !moving.length) return;
      moving.forEach((m) => m.box.node.classList.remove('lifted'));
      const was = new Map([...boxes.values()].map((box) => [box, { x: box.x, y: box.y }]));
      // Dropped frames join the shot they were dropped on, at that place in the row; below the last row they start a new shot.
      const dropped = boxes.get(id);
      const middle = dropped.y + dropped.h / 2;
      const ids = moving.map((m) => m.box.key).filter((key) => typeof key === 'number');
      const band = bands.find((b) => middle < b.y + b.h + SLATE + GAP / 2);
      const at = Math.max(0, Math.round(dropped.x / (FRAME + GAP)));
      for (const row of layout.rows) row.keys = row.keys.filter((key) => !ids.includes(key));
      insertMark.remove();
      // Dropped on the line between two shots (or above the first): a new shot there, between them.
      const fresh = gap >= 0 ? { id: ++layout.count, name: '', keys: [] } : null;
      if (fresh) layout.rows.splice(layout.rows.indexOf(bands[gap].row), 0, fresh);
      const row = fresh || (band ? band.row : newRow());
      row.keys.splice(Math.min(fresh ? 0 : at, row.keys.length), 0, ...ids);
      update();
      settleFrom(was, new Set(moving.map((m) => m.box)));
      save();
    });
  }

  // "From canvas" in a panel's + menu: what is selected, or, with nothing selected, the next frame clicked.
  let picking = null;
  const stopPicking = () => { picking = null; view.classList.remove('picking'); toolNote.classList.add('hidden'); };
  function pickFromCanvas(onPick) {
    const chosen = items.filter((i) => selected.has(i.id));
    if (chosen.length) { onPick(chosen); return; }
    picking = (item) => onPick([item]);
    clearTimeout(noteTimer);
    view.classList.add('picking');
    toolNote.replaceChildren(el('span', {}, 'Click a frame to use it'),
      el('button', { class: 'btn small quiet', onclick: stopPicking }, 'Cancel'));
    toolNote.classList.remove('hidden');
  }

  // Put items into the agent's message, opening the agent tab first when another one is showing.
  function addToChat(list) {
    if (!(isOpen() && tab === 'agent')) showPanel(true, 'agent');
    for (const item of list) agent.attach(item);
    agent.focus();
  }

  function selectionChanged() {
    agent.selectionChanged();   // the message box offers what is selected, without adding it
    for (const box of boxes.values()) box.node.classList.toggle('selected', selected.has(box.key));
    dock.refresh();
    drawOverlay();
  }

  const download = (item) => el('a', { href: `/api/library/${item.id}/file?download=true`, download: item.filename }).click();
  const open = (item) => openViewer(item, { actions: /^(edit|upload)\//.test(item.workflow) ? []
    : [{ label: 'Re-run', run: (dialog) => { dialog.close(); store.rerun = item; store.from = '/canvas'; go('/create'); } },
      seedOf(item) != null && { label: 'Reuse seed', run: (dialog) => { dialog.close(); reuseSeed(item, '/canvas'); } }].filter(Boolean) });

  async function addToTimeline(videos, button) {
    button.disabled = true;
    try {
      const board = (await api('/api/boards/timeline?project=' + project)).data;
      const clips = (board.clips || []).concat(videos.map((v) => ({ id: v.id, start: 0, end: 0 })));   // end 0 = the whole clip
      await api('/api/boards/timeline', { method: 'PUT', json: { project: project || null, data: { ...board, clips } } });
      button.textContent = 'Added';
    } catch (e) { alert(e.message); button.disabled = false; }
  }

  // ------------------------------------------------------------ what floats over the canvas

  let overlayQueued = false;
  function drawOverlay() {
    if (overlayQueued) return;
    overlayQueued = true;
    requestAnimationFrame(() => { overlayQueued = false; drawContext(); drawMap(); });
  }

  // The bar over the selection. It is built again only when the selection changes; while the board moves (every frame
  // of a pan or a glide) it is only moved.
  let contextKey = '';
  function drawContext() {
    const chosen = items.filter((i) => selected.has(i.id) && boxes.has(i.id));
    context.classList.toggle('hidden', !chosen.length);
    if (!chosen.length) { contextKey = ''; return; }
    const area = bounds(chosen.map((i) => boxes.get(i.id)));
    context.style.left = Math.max(8, cam.x + area.x * cam.k) + 'px';
    context.style.top = Math.max(56, cam.y + area.y * cam.k - 48) + 'px';
    const key = chosen.map((i) => i.id).join(',') + '|' + project;
    if (key === contextKey) return;
    contextKey = key;
    const videos = chosen.filter((i) => i.kind === 'video');
    const one = chosen.length === 1 ? chosen[0] : null;
    context.replaceChildren(...[
      !one && el('span', { class: 'slate-text' }, `${chosen.length} selected`),
      one && el('button', { class: 'btn small quiet', onclick: () => open(one) }, 'Open'),
      one && !/^(edit|upload)\//.test(one.workflow) && el('button', { class: 'btn small quiet', title: 'Open Create with the same settings',
        onclick: () => { store.rerun = one; store.from = '/canvas'; go('/create'); } }, 'Re-run'),
      one && !/^(edit|upload)\//.test(one.workflow) && seedOf(one) != null && el('button', { class: 'btn small quiet',
        title: `Seed ${seedOf(one)}: open Create with the same settings and this seed, to make the same picture with a change (Draft to Final, a word of the prompt)`,
        onclick: () => reuseSeed(one, '/canvas') }, 'Reuse seed'),
      one && seedOf(one) != null && el('span', { class: 'slate-text small' }, `Seed ${seedOf(one)}`),
      videos.length > 0 && el('button', { class: 'btn small quiet', onclick: (e) => addToTimeline(videos, e.currentTarget) },
        one ? 'Add to timeline' : `Add ${videos.length} to timeline`),
      el('button', { class: 'btn small quiet', title: 'Download (D)', onclick: () => chosen.forEach(download) }, one ? 'Download' : `Download ${chosen.length}`),
      one && project && el('button', { class: 'btn small quiet', title: `Keep it in this project's ${KIT} under a name`,
        onclick: async () => { if (await addToKitDialog({ project, item: one })) { shared.load(); dock.recast(); } } }, `Add to ${KIT}`),
    ].filter(Boolean));
  }

  // The minimap: a mark for each frame, in canvas units inside one layer that is scaled to fit, and the box of what is
  // in view. The marks are made again only when frames move or the selection changes; a moving camera only changes the
  // layer's scale and the box.
  const mapLayer = el('div', { class: 'minimap-layer' });
  const mapView = el('b');
  map.append(mapLayer, mapView);
  let mapKey = '';
  function drawMap() {
    map.classList.toggle('hidden', boxes.size < 2);
    if (boxes.size < 2) return;
    const marks = [...boxes.values()];
    const key = marks.map((b) => `${b.key}:${b.x}:${b.y}:${b.h}:${selected.has(b.key) ? 1 : 0}`).join('|');
    if (key !== mapKey) {
      mapKey = key;
      mapLayer.replaceChildren(...marks.map((b) => el('i', { class: selected.has(b.key) ? 'on' : '', style: `left:${b.x}px;top:${b.y}px;width:${FRAME}px;height:${b.h}px` })));
    }
    const rect = stage.getBoundingClientRect();
    const seen = { x: -cam.x / cam.k, y: -cam.y / cam.k, h: rect.height / cam.k, right: (rect.width - cam.x) / cam.k, bottom: (rect.height - cam.y) / cam.k };
    const all = bounds([...boxes.values()]);
    const left = Math.min(all.x, seen.x);
    const top = Math.min(all.y, seen.y);
    const scale = Math.min(120 / (Math.max(all.right, seen.right) - left), 72 / (Math.max(all.bottom, seen.bottom) - top));
    mapLayer.style.transform = `scale(${scale}) translate(${-left}px, ${-top}px)`;
    mapView.style.cssText = `left:${(seen.x - left) * scale}px;top:${(seen.y - top) * scale}px;width:${(seen.right - seen.x) * scale}px;height:${(seen.bottom - seen.y) * scale}px`;
  }

  // ------------------------------------------------------------ loading and saving

  let saveTimer;
  function save() {
    agent.redraw();   // where each of the agent's results is ("Shot 3 › Take 2") may have changed
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => api('/api/boards/canvas', { method: 'PUT', json: { project: project || null, data: layout } }).catch(() => {}), 400);
  }

  async function loadItems() {
    const [library, core, boards] = await Promise.all([api('/api/library?all=1' + (project ? '&project=' + project : '')),
      project ? api('/api/kit?project=' + project).catch(() => ({ entries: [] })) : { entries: [] },
      api('/api/library/placement?project=' + project).catch(() => ({ boards: [] }))]);
    items = library.items;
    placed = { boards: Array.isArray(boards.boards) ? boards.boards : [] };
    kitEntries = (core.entries || []).filter((e) => !e.hidden);
    for (const id of [...selected]) if (!items.some((i) => i.id === id)) selected.delete(id);
  }

  async function load() {
    ready = false;
    for (const [id, frame] of jobFrames) { frame.node.remove(); boxes.delete('job:' + id); }
    jobFrames.clear();
    try {
      projects = (await api('/api/projects')).projects;
      if (project && !projects.some((p) => p.id === project)) project = 0;
      {
        const here = projects.find((p) => p.id === project);
        picker.textContent = here ? (here.parent_name ? `${here.parent_name} › ${here.name}` : here.canvas_name ? `${here.name} › ${here.canvas_name}` : here.name) : 'All work';
        picker.onclick = here ? () => go(placePath('/project', here)) : null;
        picker.classList.toggle('linked', !!here);
        showAddress(placePath('/canvas', here));   // the address names this project and module, to keep or send
        timelineLink.href = placePath('/timeline', here);
        shareButton.classList.toggle('hidden', !project);   // a NeuralCore belongs to a project: none for all work
        picker.title = here ? 'Open the project: its NeuralCore and its modules' : 'Everything you have made';
      }
      tabTitle((projects.find((p) => p.id === project) || { name: 'Canvas' }).name);
      const [board] = await Promise.all([api('/api/boards/canvas?project=' + project), loadItems()]);
      const saved = board.data || {};
      layout = { rows: Array.isArray(saved.rows) ? saved.rows.filter((row) => row && Array.isArray(row.keys)) : [], count: Number(saved.count) || 0,
        picks: saved.picks && typeof saved.picks === 'object' && !Array.isArray(saved.picks) ? saved.picks : {} };
      ready = true;
      draw();
      fit();
    } catch (e) { hint.textContent = e.message; hint.classList.remove('hidden'); }
  }

  const onKey = (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'j') { e.preventDefault(); return showPanel(!isOpen()); }
    if (e.target.closest('input, textarea, select, dialog, [contenteditable]') || e.metaKey || e.ctrlKey) return;
    if (e.key === '1') fit(true);
    else if (e.key === '0') zoomTo(1);
    else if (e.key === 'Escape' && picking) stopPicking();
    else if (e.key === 'Escape' && selected.size) { selected.clear(); selectionChanged(); }
    else if (e.key === 'Enter' && selected.size === 1) open(items.find((i) => selected.has(i.id)));
    else if (e.key.toLowerCase() === 'd' && !e.altKey && !e.repeat) items.filter((i) => selected.has(i.id)).forEach(download);
  };
  window.addEventListener('keydown', onKey);
  const ticker = setInterval(() => {   // keeps elapsed time moving
    for (const job of store.jobs) if (job.status === 'running' && jobFrames.has(job.id)) jobFrames.get(job.id).clock.textContent = elapsed(job);
  }, 1000);
  const unsubscribe = subscribe((change) => {
    if (!ready) return;
    if (change === 'jobs') update();
    if (change === 'library') loadItems().then(draw).catch(() => {});
  });

  applyCamera();
  load();
  setWidth(Number(localStorage.getItem('scene.panel.width')));
  showPanel(true);
  return () => {
    unsubscribe();
    dock.destroy();
    agent.destroy();
    shared.destroy();
    clearInterval(ticker);
    clearTimeout(saveTimer);
    lazy.disconnect();
    window.removeEventListener('keydown', onKey);
    leaveBalance();
    view.classList.remove('full', 'with-panel', 'resizing', 'agent-full');
    view.style.removeProperty('--panel-w');
  };
}
