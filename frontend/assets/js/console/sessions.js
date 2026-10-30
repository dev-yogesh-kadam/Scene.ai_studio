// The console's Sessions section (admins only): every agent tab's Claude session, what it is doing now, and what
// happened in it, watched as it happens. /sessions lists them; /sessions/SES... watches one, and
// /sessions/SESa,SESb several side by side. Watch only: nothing here writes to a session. See backend/scene/sessions.py.

import { api } from '../api.js';
import { el } from '../dom.js';
import { go, here } from '../nav.js';
import { number, ago, stamp, table, searchBox, person } from './shared.js';

const STATES = [{ id: '', label: 'All' }, { id: 'answering', label: 'Answering' }, { id: 'live', label: 'Live' },
  { id: 'idle', label: 'Idle' }, { id: 'deleted', label: 'Deleted' }];
const STATE_PILL = { answering: 'running', live: 'done', idle: 'cancelled', deleted: 'failed' };
const KIND = { user: 'User', prompt: 'Sent', thinking: 'Thinking', text: 'Claude', tool_call: 'Tool', tool_result: 'Result',
  answer: 'Answer', compact: 'Compact', model: 'Model', error: 'Error', note: 'Note' };
const FOLDED = new Set(['prompt', 'thinking', 'tool_result']);   // long: shown folded, opened with a click
const POLL = 2000;
const tokens = (n) => (n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? Math.round(n / 1e3) + 'k' : number(n));
const statePill = (s) => el('span', { class: 'pill ' + (STATE_PILL[s] || '') }, s[0].toUpperCase() + s.slice(1));
const watched = () => (here().split('/')[2] || '').split(',').filter((r) => /^SES[A-Za-z0-9]{13}$/.test(r));
const where = (s) => (s.parent_name ? `${s.parent_name} › ${s.project_name}` : s.project_name || 'All work');

function fullness(s) {
  const share = Math.min(100, s.percent || 0);
  return el('div', { class: 'ses-meter', title: `${number(s.context_tokens)} of ${number(s.context_window)} tokens` },
    el('div', { class: 'bar-track' }, el('div', { class: 'bar-value' + (share >= 80 ? ' high' : ''), style: `width:${share}%` })),
    el('span', { class: 'muted small' }, `${share}%` + (s.compacts ? ` · compacted ${s.compacts}×` : '')));
}

export async function sessions(ctx) {
  const refs = watched();
  return refs.length ? watch(refs) : list(ctx);
}

// ---------------------------------------------------------------- the list

async function list(ctx) {
  const s = ctx.state.sessions;
  const picked = new Set();
  const found = await api(`/api/admin/sessions?q=${encodeURIComponent(s.q)}&state=${s.state}`);
  const rows = found.sessions;
  const watchButton = el('button', { class: 'btn small primary', disabled: true, onclick: () => go('/sessions/' + [...picked].join(',')) },
    'Watch side by side');
  const tick = (row) => el('input', { type: 'checkbox', 'aria-label': 'Pick ' + row.ref, onclick: (e) => {
    e.stopPropagation();
    if (e.target.checked) picked.add(row.ref); else picked.delete(row.ref);
    watchButton.disabled = picked.size < 1;
    watchButton.textContent = picked.size > 1 ? `Watch ${picked.size} side by side` : 'Watch side by side';
  } });
  const chips = el('div', { class: 'chips' }, STATES.map((st) => el('button', {
    class: 'btn small' + (s.state === st.id ? ' primary' : ''), onclick: () => { s.state = st.id; ctx.draw(); } },
  st.label + (st.id && found.counts[st.id] ? ` · ${found.counts[st.id]}` : ''))));
  const node = el('div', { class: 'card' },
    el('div', { class: 'card-head' }, el('h2', {}, 'Claude sessions'),
      searchBox('Session, tab, project id, person or email', s.q, (v) => { s.q = v; ctx.draw(); })),
    el('div', { class: 'row', style: 'margin-bottom:10px' }, chips, el('span', { style: 'flex:1' }), watchButton),
    table(['', 'Session', 'Person', 'Project', 'Model', 'Context', 'Messages', 'Now', 'Last active'], rows.map((r) => [
      tick(r), person(r.title || 'Studio session', r.ref), person(r.user_name, r.user_email),
      person(where(r), [r.parent_ref, r.project_ref].filter(Boolean).join(' › ') || ''), r.model || '—', fullness(r), number(r.messages),
      statePill(r.state), ago(r.active)]),
    { onRow: (i) => go('/sessions/' + rows[i].ref), empty: s.q || s.state ? 'No session matches.' : 'No agent tab has used Claude yet.' }),
    el('p', { class: 'muted small', style: 'margin-top:10px' },
      'One session for each agent tab of a project. It goes on across days and model changes, and is compacted, still the same session, ' +
      'when its context is 90% full. Nothing is ever deleted here. Watch only.'));
  // The list follows what the sessions do while it is open.
  const timer = setInterval(() => { if (!node.isConnected) clearInterval(timer); else if (!picked.size && !document.hidden) ctx.draw(); }, 5000);
  return [node];
}

// ---------------------------------------------------------------- watching sessions

function watch(refs) {
  const grid = el('div', { class: 'ses-grid' + (refs.length > 1 ? ' many' : '') }, refs.map((ref) => pane(ref, refs.length === 1)));
  return [el('div', { class: 'row', style: 'margin-bottom:12px' },
    el('a', { class: 'btn small', href: '/sessions' }, '← All sessions'),
    el('span', { class: 'muted small' }, refs.length > 1 ? `${refs.length} sessions side by side, as they happen` : 'As it happens')), grid];
}

function pane(ref, alone) {
  const head = el('div', { class: 'ses-head' }, el('b', {}, ref));
  const facts = el('div', { class: 'ses-facts' });
  const log = el('div', { class: 'ses-log', role: 'log', 'aria-live': 'polite' });
  const node = el('div', { class: 'card ses-pane' + (alone ? ' alone' : '') }, head, facts, log);
  let after = 0;
  let timer = null;
  const born = Date.now();
  const gone = () => !node.isConnected && Date.now() - born > 5000;   // left the page (not: not on it yet)

  const copy = (text, button) => {
    navigator.clipboard.writeText(text).then(() => { button.textContent = 'Copied'; setTimeout(() => { button.textContent = 'Copy'; }, 1500); },
      () => { button.textContent = 'Select it and copy'; });
  };
  const drawFacts = (s) => {
    head.replaceChildren(el('div', { class: 'grow' }, el('b', {}, s.title || 'Studio session'), el('div', { class: 'muted small' }, s.ref)),
      statePill(s.state));
    const resume = s.resume && el('div', { class: 'ses-resume' }, el('code', {}, s.resume),
      el('button', { class: 'btn small', onclick: (e) => copy(s.resume, e.currentTarget) }, 'Copy'));
    facts.replaceChildren(
      el('dl', { class: 'facts' },
        el('dt', {}, 'Person'), el('dd', {}, `${s.user_name} · ${s.user_email}`),
        el('dt', {}, 'Project'), el('dd', {}, where(s) + (s.project_ref ? ` (${[s.parent_ref, s.project_ref].filter(Boolean).join(' › ')})` : '')),
        el('dt', {}, 'Agent tab'), el('dd', {}, s.agent),
        el('dt', {}, 'Claude session'), el('dd', {}, s.claude_id || 'not started yet'),
        el('dt', {}, 'Model'), el('dd', {}, s.model || '—'),
        el('dt', {}, 'Context'), el('dd', {}, fullness(s), el('span', { class: 'muted small' }, `${tokens(s.context_tokens)} of ${tokens(s.context_window)}`)),
        el('dt', {}, 'Messages'), el('dd', {}, number(s.messages)),
        el('dt', {}, 'Started'), el('dd', {}, stamp(s.started)),
        el('dt', {}, 'Last active'), el('dd', {}, ago(s.active))),
      resume || '');
  };
  const line = (e) => {
    const long = FOLDED.has(e.kind) || e.text.length > 600;
    let text = e.text;
    if (e.kind === 'tool_call' && e.data && e.data.input) text = `${e.text}(${JSON.stringify(e.data.input)})`;
    if (e.kind === 'answer' && e.data) text += e.data.steps ? `\n(${e.data.steps} step${e.data.steps === 1 ? '' : 's'} planned)` : '';
    if (e.kind === 'compact' && e.data && e.data.pre_tokens) text += ` · ${tokens(e.data.pre_tokens)} → ${tokens(e.data.post_tokens || 0)} tokens`;
    const body = long
      ? el('details', {}, el('summary', {}, text.split('\n')[0].slice(0, 160) || '(empty)', el('span', { class: 'muted' }, ` · ${number(text.length)} characters`)),
        el('pre', {}, text))
      : el('pre', {}, text);
    return el('div', { class: 'ses-line k-' + e.kind },
      el('span', { class: 'ses-time', title: stamp(e.at) }, new Date(e.at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' })),
      el('span', { class: 'ses-kind' }, KIND[e.kind] || e.kind), body);
  };

  async function poll() {
    if (gone()) return;
    try {
      const got = await api(`/api/admin/sessions/${ref}?after=${after}`);
      drawFacts(got.session);
      const atEnd = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
      if (!after && !got.events.length) log.replaceChildren(el('p', { class: 'muted' }, 'Nothing has happened in this session yet.'));
      else if (!after) log.replaceChildren();
      log.append(...got.events.map(line));
      if (got.events.length) after = got.events[got.events.length - 1].id;
      if (atEnd || got.events.length === 500) log.scrollTop = log.scrollHeight;
      if (got.more) { timer = setTimeout(poll, 50); return; }   // a long story comes in pages
    } catch (e) {
      log.replaceChildren(el('p', { class: 'error' }, e.message));
      if (e.status === 404) return;
    }
    if (!gone()) timer = setTimeout(poll, document.hidden ? POLL * 5 : POLL);
  }
  poll();
  return node;
}
