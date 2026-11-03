// Sign in and create account.

import { api } from '../api.js';
import { el, field } from '../dom.js';
import * as scenes from './landing-scenes.js';
import { READOUT, frameTimecode, sections, smooth, keepPrompt } from './landing.js';

const POINTS = [
  'Turn a prompt and a few reference images into video',
  'Chain clips into longer scenes that stay consistent',
  'Keep your characters, outfits and voices to reuse',
];

export async function renderAuth(root, onSignedIn, start = 'login') {
  let info = { first_run: false, signup_open: false };
  try { info = await api('/api/auth/state'); } catch (e) { /* show sign-in anyway */ }
  let mode = start;   // 'login' or 'register'
  let second = null;   // {email, password} once the password was right and an authenticator code is asked for

  const draw = (message) => {
    if (second) return drawCode(message);
    const register = mode === 'register';
    const name = el('input', { type: 'text', autocomplete: 'name', placeholder: 'Your name' });
    const email = el('input', { type: 'email', autocomplete: 'email', required: true, placeholder: 'you@company.com' });
    const password = el('input', { type: 'password', required: true, minlength: register ? 8 : null,
      autocomplete: register ? 'new-password' : 'current-password', placeholder: register ? 'At least 8 characters' : 'Your password' });
    const error = el('p', { class: 'error notice' }, message || '');
    const submit = el('button', { class: 'btn primary block', type: 'submit' }, register ? 'Create account' : 'Sign in');

    const form = el('form', { onsubmit: async (e) => {
      e.preventDefault();
      submit.disabled = true;
      try {
        const user = await api(register ? '/api/auth/register' : '/api/auth/login',
          { method: 'POST', json: { name: name.value, email: email.value, password: password.value } });
        onSignedIn(user);
      } catch (err) {
        if (!register && err.data && err.data.mfa_required) {
          second = { email: email.value, password: password.value };
          return draw();
        }
        error.textContent = err.message;
        submit.disabled = false;
      }
    } },
      register && field('Name', name),
      field('Email', email),
      field('Password', password),
      error, submit);

    page(register ? 'New account' : 'Sign in', el('h1', {}, register ? (info.first_run ? 'Set up Scene.ai' : 'Create your account') : 'Welcome back'),
      el('p', { class: 'muted' }, !register ? 'Sign in to your studio.' : info.first_run
        ? 'Create the first account. It becomes the admin of this installation.'
        : 'It takes a few seconds.'),
      form,
      info.signup_open && el('div', { class: 'auth-switch muted' },
        register ? 'Already have an account? ' : 'New here? ',
        el('button', { type: 'button', onclick: () => { mode = register ? 'login' : 'register'; draw(); } },
          register ? 'Sign in' : 'Create an account')));
    (register ? name : email).focus();
  };

  // The second step: a code from the authenticator app, or one of the recovery codes.
  const drawCode = (message) => {
    const code = el('input', { type: 'text', inputmode: 'numeric', autocomplete: 'one-time-code', required: true, maxlength: 20,
      placeholder: '123456' });
    const error = el('p', { class: 'error notice' }, message || '');
    const submit = el('button', { class: 'btn primary block', type: 'submit' }, 'Sign in');
    const form = el('form', { onsubmit: async (e) => {
      e.preventDefault();
      submit.disabled = true;
      try {
        onSignedIn(await api('/api/auth/login', { method: 'POST', json: { ...second, code: code.value } }));
      } catch (err) {
        error.textContent = err.message;
        submit.disabled = false;
        code.select();
      }
    } }, field('Code', code), error, submit);
    page('Two-step', el('h1', {}, 'Two-step sign-in'),
      el('p', { class: 'muted' }, 'Enter the 6-digit code your authenticator app shows for Scene.ai. Lost the phone? Use one of your recovery codes.'),
      form,
      el('div', { class: 'auth-switch muted' },
        el('button', { type: 'button', onclick: () => { second = null; draw(); } }, 'Back')));
    code.focus();
  };

  // The landing's buttons further down the page lead back up to the form, on the side they name.
  const openForm = (to) => {
    second = null;
    mode = to;
    draw();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };
  const toForm = (to, label) => (cls = '') => el('button', { type: 'button', class: 'la-btn ' + cls, onclick: () => openForm(to) }, label);
  const signIn = toForm('login', 'Sign in');
  const join = info.signup_open ? toForm('register', 'Create an account') : signIn;
  // A prompt picked further down waits for after signing in (it fills Home's prompt box); the form comes up to get there.
  const pick = (text) => { keepPrompt(text); openForm(info.signup_open ? 'register' : 'login'); };

  let set = null;
  const page = (tag, ...card) => {
    if (!set || !set.node.isConnected) {
      set = signInSet({ scene: 'desert', home: '/', heading: ['Direct', el('br'), 'your ', el('b', {}, 'scene.')],
        sub: 'Write the shot. The studio makes the takes, keeps the same faces from shot to shot, and cuts them together.',
        points: POINTS, below: sections(join, signIn, info.signup_open, pick) });
      root.replaceChildren(set.node);
      smooth(set.node);
    }
    set.tag.textContent = tag;
    set.card.replaceChildren(...card.filter(Boolean));   // a part left out (no sign-up link) is false, not text
  };
  draw();
}

// The sign-in pages are the landing page's monitor held on one scene: its frame lines, the camera's readouts and a
// running timecode, the headline at the lower left and, where the landing has the slate, the form. The admin
// console's sign-in is drawn with it too; the studio's has the landing's sections below. Returns the page, the slate's
// body to put the form in, and its tag.
export function signInSet({ scene, home, heading, sub, points, below = [] }) {
  const frame = el('div', { class: 'la-frame', 'aria-hidden': 'true' });
  frame.innerHTML = scenes.svg(scene);   // the page's own drawing, never anyone's input
  const tc = el('span', { class: 'la-rec' }, '01:00:00:00');
  const tag = el('span');
  const card = el('div', { class: 'auth-card' });
  const brand = [el('img', { src: '/assets/img/logo.svg?v=clapper', alt: '' }), 'Scene.ai'];
  const node = el('div', { class: 'la auth-set' }, el('section', { class: 'la-monitor' },
    frame, el('div', { class: 'la-grade' }), el('div', { class: 'la-grain' }),
    el('div', { class: 'la-hud', 'aria-hidden': 'true' }, ['tl', 'tr', 'bl', 'br'].map((c) => el('i', { class: 'la-corner la-' + c })),
      el('div', { class: 'la-thirds' }), el('div', { class: 'la-cross' })),
    el('header', { class: 'la-top' },
      home ? el('a', { class: 'la-brand', href: home, title: 'About Scene.ai' }, ...brand) : el('span', { class: 'la-brand' }, ...brand),
      el('div', { class: 'la-readout la-mono', 'aria-hidden': 'true' }, tc, READOUT[scene].map((t) => el('span', {}, t))),
      el('span', { class: 'auth-spacer' })),
    el('div', { class: 'la-lower' },
      el('div', {},
        el('h2', { class: 'la-head' }, ...heading),
        el('p', { class: 'la-sub' }, sub),
        el('ul', { class: 'auth-points la-mono' }, points.map((p) => el('li', {}, p)))),
      el('div', { class: 'la-slate auth-slate' }, el('header', { class: 'la-mono' }, tag, el('span', {}, 'Scene.ai')), card)),
    el('div', { class: 'la-meters', 'aria-hidden': 'true' }, el('i'), el('i'), el('i'))), ...below);

  // The timecode runs at 24 frames a second, and stops once the page is left.
  const started = performance.now();
  const tick = () => {
    if (!node.isConnected && node.dataset.placed) return;
    if (node.isConnected) node.dataset.placed = '1';
    tc.textContent = frameTimecode(Math.floor((performance.now() - started) / (1000 / 24)) + 24 * 3600);
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
  return { node, card, tag };
}
