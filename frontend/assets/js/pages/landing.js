// The landing page: what a visitor who is not signed in sees at the site's address. The first screen is a camera
// monitor on the set: the frame is a scene, with frame lines, a timecode that runs, the lens and light readouts, and a
// slate where the plan of the shot types itself. Each scene is made as the studio makes one: the storyboard, Approve,
// the takes rendering, then its three shots, each a camera move through the set (drawn in layers, landing-set.js, or
// built in 3D where the browser can, landing-3d.js); the shot rows play a shot, the scene buttons cut the whole set,
// and the set has its sound (landing-sound.js). Scrolling folds the monitor away and lays its shots out on a timeline.
// Below that, plain sections in the monitor's language: the take report, the agent, what is on the cart, the price,
// and the cut. Everything it shows is something the studio does; the pictures are drawn by the page itself
// (landing-scenes.js), so it needs no media files.

import { el } from '../dom.js';
import { go } from '../nav.js';
import * as scenes from './landing-scenes.js';
import { drawnSet } from './landing-set.js';
import { sound } from './landing-sound.js';

// What can be made, with the models that make it. Kept in step with workflows/ (see docs/HANDOVER.md, Workflows).
const KIT = [
  ['Video', 'Clips with sound', 'MiniMax H3 · LTX-2.5', 'Clips of 5 to 15 seconds from a prompt and up to eight references: a character, an outfit, a place, a motion to copy, a voice. Chain clips into longer scenes that pick up where the last one ended.'],
  ['People', 'Talking and moving', 'Talking Head · Lip Sync · Wan Animate 2', 'A portrait that speaks a voice track, a clip whose lips meet new words, a character doing the moves of a video you give it.'],
  ['Restyle', 'A new look, the same motion', 'LTX-2.3 IC-LoRA · Wan 2.2 Fun · Wan VACE', 'Keep how a video moves and change how it looks, or widen it into a new shape with the edges filled in.'],
  ['Images', 'Stills and posters', 'FLUX.2 · FLUX 3 Klein · Qwen Image 2.1 · Hunyuan 2.1 · Krea 2', 'Stills from a prompt and up to four reference pictures, so a character looks the same in every one.'],
  ['Sound', 'Songs, voices and words', 'MiniMax Music 3 · Separate voice · Transcribe', 'Songs from 30 seconds to 5 minutes, with your lyrics or without; a voice lifted out of the music; a transcript with times and speakers.'],
  ['Titles', 'Motion graphics', 'Drawn in the studio', 'Title cards, lower thirds and whole videos of animated words, written from a sentence and editable scene by scene.'],
  ['Finish', 'Upscale', 'SeedVR2', 'A finished video made larger and sharper, up to four times its size.'],
];

// Your first video, as the guide tells it (docs/guide.md, section 2).
const STEPS = [
  ['Say what you want', 'Type the shot, or tell the agent about the whole film. Add reference pictures if you have them.'],
  ['Approve the plan', 'Every step comes with its model and its price. Nothing runs until you press Approve.'],
  ['Every take is checked', 'Wrong face, broken hands, the wrong place: the take is flagged and can be retaken with a new approach.'],
  ['Cut and export', 'The agent puts the shots in order, music under them, titles on top. One finished video.'],
];

// What people make with it, each with a prompt to start from. The picture is one of the drawn scenes.
const USES = [
  ['rooftop', 'Ads and product videos', 'A 20 second ad for our sneaker drop. Rooftop at golden hour, the same runner in every shot.'],
  ['neon', 'Reels, Shorts and TikToks', 'A 9:16 Reel: a street food vendor in Mumbai at night, neon, quick cuts on the beat.'],
  ['desert', 'Short films from a script', 'Turn my script into a 1 minute short. Two travellers, an old jeep, a desert at noon.'],
  ['deep', 'Explainers from an article', 'Make a 45 second vertical explainer of this article, with a voiceover and captions.'],
  ['rooftop', 'Talking heads and dialogue', 'My founder portrait says this welcome line, lips in time, a soft office behind her.', true],
  ['neon', 'Music videos', 'A 30 second synthwave track and a neon city drive cut to it.', true],
  ['desert', 'A new look for your video', 'Keep how my clip moves, make it look like a hand-painted film.', true],
  ['deep', 'Titles and motion graphics', 'An intro card and lower thirds for my podcast, clean and bold.', true],
];

// What the agent does besides planning (docs/agent-features-2026-11.md, docs/guide.md section 11).
const AGENT = ['Plans whole films, ads and Reels', 'Prices every step first', 'Looks at every take',
  'Retakes a failed shot', 'Makes variations side by side', 'Researches on the web, with sources', 'Explains the craft when you ask',
  'Asks a second opinion'];

// After the take: the rest of the studio.
const BENCH = [
  ['Canvas', 'One row per shot', 'Results land in the row of their shot; takes stack newest on top, so the board reads like a shot list.'],
  ['Final cut', 'A finished film', 'Trim, order, add music. Fades, music ducked under speech and even loudness, in one export.'],
  ['Long runs', 'Films made step by step', 'A script becomes a film over many turns. It carries on by itself, and another tab or teammate can pick it up.'],
  ['Shape', 'Any screen', 'A video cropped to 9:16, 1:1, 4:5 or 16:9 around what matters, or widened with the new space filled in.'],
  ['Free', 'Edits on the house', 'Trims, joins, subtitles burned in, retimes to a voice track and proof sheets run on the studio, at no cost.'],
  ['Teams', 'Projects with people', 'Invite members to a project with a role, share what you made, and keep one memory for the whole team.'],
];

// Questions before signing up, answered from what the studio does.
const FAQ = [
  ['Do I need to know ComfyUI or own a GPU?', 'No. The studio runs the models on its render PC. You write, look and choose; there is no node graph to wire.'],
  ['Will my character look the same from shot to shot?', 'That is what NeuralCore is for. Keep a face, an outfit, a place or a voice once, and every later shot of it uses that picture.'],
  ['What does it cost?', 'Credits, for what you make: a set price per picture, a price per second for video and music. You see the price before you press Generate.'],
  ['What if a take comes out wrong?', 'A job that fails or is cancelled gives its credits back. The agent checks each take it planned and offers a retake when something is off.'],
  ['Can my team work in the same project?', 'Yes. A project has members with roles, its own canvases and memory, so anyone on it can carry on the work.'],
];

// The camera's readouts for each scene: lens and stop, sensitivity and shutter, colour temperature.
export const READOUT = { rooftop: ['35mm · T2.0', 'ISO 800 · 1/48', '3200K'], neon: ['24mm · T1.4', 'ISO 1600 · 1/48', '5600K'],
  desert: ['85mm · T5.6', 'ISO 100 · 1/96', '6500K'], deep: ['18mm · T2.8', 'ISO 3200 · 1/48', '4300K'] };

// Four takes of one shot for the take report: what each was, and the one that was kept.
const TAKES = [['rooftop', 'Take 1', '6.0 s', 'Rejected · face', 'dull'], ['rooftop', 'Take 2', '6.0 s', 'Soft focus', 'soft'],
  ['rooftop', 'Take 3', '6.0 s', 'Kept', 'kept'], ['neon', 'Take 4', '5.0 s', 'New seed', '']];

const still = () => document.documentElement.dataset.motion === 'calm';   // the Motion setting (theme.js)
const calmNow = () => still() || matchMedia('(prefers-reduced-motion: reduce)').matches;

// A picture the studio draws: one of the landing scenes, filling its box. The markup is the page's own, never anyone's input.
function picture(name, cls = '', sketch = false) {
  const node = el('div', { class: cls, 'aria-hidden': 'true' });
  node.innerHTML = scenes.svg(name, { sketch });
  return node;
}

// The frame counter of the camera: hours, minutes, seconds and frames at 24 a second, from one hour in.
export function frameTimecode(frames) {
  const two = (n) => String(n).padStart(2, '0');
  return `${two(Math.floor(frames / 86400) % 24)}:${two(Math.floor(frames / 1440) % 60)}:${two(Math.floor(frames / 24) % 60)}:${two(frames % 24)}`;
}

// How a scene is made on the monitor, as the studio makes it: the storyboard first while the plan types itself, then
// Approve, then the takes render (the colour wipes across the sketch), then the three shots play, each a camera move.
const BOARD = 2800, APPROVE = 500, RENDER = 1700, SWAP = 650;   // ms; the set changes under the sketch at SWAP
// A real take of each scene from the render PC, to play over the drawn set while its shots run: scene name → its
// address under /assets/landing/. None has been made yet; the drawn and 3D sets stand in.
const CLIPS = {};
const SET_KEY = 'scene.landingSet';   // '3d' or 'drawn', when the visitor picked one

// Can this browser show the 3D sets? WebGL, the full motion setting and a screen wide enough for the monitor.
function canThree() {
  if (calmNow() || window.innerWidth < 900) return false;
  try { return !!document.createElement('canvas').getContext('webgl2'); } catch (e) { return false; }
}

function monitor(join, signupOpen, start) {
  const calm = calmNow();
  const set = drawnSet();
  const canvas = el('canvas', { class: 'la-3d', 'aria-hidden': 'true' });
  const take = document.createElement('video');
  Object.assign(take, { muted: true, loop: true, playsInline: true, className: 'la-real' });
  const board = el('div', { class: 'la-board', 'aria-hidden': 'true' });
  const wipe = el('i', { class: 'la-wipe', 'aria-hidden': 'true' });
  const flash = el('i', { class: 'la-flash', 'aria-hidden': 'true' });
  const frame = el('div', { class: 'la-set' }, set.node, canvas, take, board, wipe, flash);

  const tc = el('span', { class: 'la-rec' }, '01:00:00:00');
  const lens = el('span'), iso = el('span'), wb = el('span');
  const moveName = el('b'), moveBar = el('i');
  const move = el('div', { class: 'la-move la-mono', 'aria-hidden': 'true' }, moveName, moveBar);
  const sceneName = el('span'), state = el('span');
  const typed = el('div', { class: 'la-typed', 'aria-hidden': 'true' });
  const rows = el('ol');
  const note = el('span', { class: 'la-mono' }), approve = el('span', { class: 'la-btn solid small' });
  const buttons = scenes.names.map((name, i) => el('button', { type: 'button', 'aria-pressed': 'false',
    onclick: () => { touched = true; cut(i); } }, `${i + 1} · ${scenes.info(name).title}`));
  const modeButtons = ['3d', 'drawn'].map((m) => el('button', { type: 'button', 'aria-pressed': 'false', onclick: () => pickMode(m, true) },
    m === '3d' ? '3D' : 'Drawn'));
  const modes = el('span', { class: 'la-modes hidden', role: 'group', 'aria-label': 'Set' }, el('span', { class: 'la-mono' }, 'Set'), modeButtons);
  const bars = [0, 1, 2, 3, 4].map(() => el('i'));
  const noise = sound();
  const soundButton = el('button', { type: 'button', class: 'la-sound la-mono', 'aria-pressed': 'false', title: 'The sound of the set',
    onclick: () => {
      if (noise.on) noise.stop(); else noise.start(scenes.names[current]);
      soundButton.setAttribute('aria-pressed', String(noise.on));
      soundLabel.textContent = noise.on ? 'Sound on' : 'Sound off';
    } }, el('span', { 'aria-hidden': 'true' }, bars));
  const soundLabel = el('span', {}, 'Sound off');
  soundButton.append(soundLabel);

  const node = el('section', { class: 'la-monitor' },
    frame, el('div', { class: 'la-grade' }), el('div', { class: 'la-grain' }),
    el('div', { class: 'la-chrome' },
      el('div', { class: 'la-hud', 'aria-hidden': 'true' }, ['tl', 'tr', 'bl', 'br'].map((c) => el('i', { class: 'la-corner la-' + c })),
        el('div', { class: 'la-thirds' }), el('div', { class: 'la-cross' })),
      el('header', { class: 'la-top' },
        el('a', { class: 'la-brand', href: '/' }, el('img', { src: '/assets/img/logo.svg?v=clapper', alt: '' }), 'Scene.ai'),
        el('div', { class: 'la-readout la-mono', 'aria-hidden': 'true' }, tc, lens, iso, wb),
        el('nav', { class: 'la-doors' },
          signupOpen && el('a', { class: 'la-btn quiet', href: '/signin' }, 'Sign in'),
          join('solid'))),
      move,
      el('div', { class: 'la-lower' },
        el('div', {},
          el('h1', {}, 'Direct', el('br'), 'your ', el('b', {}, 'scene.')),
          el('p', { class: 'la-sub' }, 'Write the shot. The studio makes the takes, keeps the same faces from shot to shot, and cuts them together, without a node graph in sight.'),
          ask(start)),
        el('div', { class: 'la-slate' },
          el('header', { class: 'la-mono', 'aria-hidden': 'true' }, sceneName, state),
          typed, rows,
          el('footer', { 'aria-hidden': 'true' }, note, approve))),
      el('div', { class: 'la-scenes', role: 'group', 'aria-label': 'Scene' }, el('span', { class: 'la-mono' }, 'Scene'), buttons, modes),
      soundButton));

  // Under the monitor: the same scene as its three shots on a timeline. On a wide screen scrolling folds the monitor
  // into the corner and lays the shots out under it (the reel); elsewhere it is a plain section after the monitor.
  const cutLabel = el('span');
  const ruler = el('div', { class: 'la-ruler la-mono', 'aria-hidden': 'true' });
  const clips = el('div', { class: 'la-clips' });
  const head = el('i', { class: 'la-head', 'aria-hidden': 'true' });
  const wave = el('div', { class: 'la-wave', 'aria-hidden': 'true' },
    Array.from({ length: 140 }, (_, i) => el('i', { style: `height:${(18 + Math.abs(Math.sin(i * 0.37) * 52 + Math.sin(i * 1.7) * 18)).toFixed(0)}%` })));
  const cutline = el('div', { class: 'la-cutline' },
    el('div', { class: 'la-cut-copy' },
      el('div', { class: 'la-mono la-cut-label' }, cutLabel),
      el('h2', {}, 'One prompt.', el('br'), el('b', {}, 'Three shots, one cut.')),
      el('p', {}, 'The scene above was planned as these three shots: each one a camera move on the same set, with the same runner, cut together with sound. Pick a shot to play it.')),
    el('div', { class: 'la-track' }, ruler, el('div', { class: 'la-lanes' }, clips, wave, head)));
  const pin = el('div', { class: 'la-reel-pin' }, node, cutline);
  const reel = el('div', { class: 'la-reel' }, pin);

  let current = -1, phase = 'shots', shot = 0, phaseAt = 0, swapped = true, touched = false, typing = null;
  let mode = 'drawn', three = null;
  const camera = () => scenes.info(scenes.names[current]).camera;
  const shotSeconds = () => camera().reduce((n, c) => n + c.dur, 0) / 1000;

  function type(text) {
    clearInterval(typing);
    if (calm) { typed.textContent = text; return; }
    let n = 0;
    typing = setInterval(() => { typed.textContent = text.slice(0, ++n); if (n >= text.length) clearInterval(typing); }, 32);
  }

  // The slate's shot rows and the timeline's clips: buttons that play that shot.
  function drawShots(name) {
    const info = scenes.info(name);
    rows.replaceChildren(...info.shots.map((title, n) => el('li', {}, el('button', { type: 'button', class: 'la-shot', 'aria-label': `Play shot ${n + 1}: ${title}`,
      onclick: () => { touched = true; play(n); } }, el('span', {}, `0${n + 1}`), el('span', {}, title), el('span', {}, '60 cr')))));
    clips.replaceChildren(...info.shots.map((title, n) => {
      const c = info.camera[n].to;
      const pic = picture(name, 'la-clip-pic');
      pic.style.transformOrigin = `${(c.fx / 16).toFixed(1)}% ${(c.fy / 9).toFixed(1)}%`;
      pic.style.transform = `scale(${c.k.toFixed(2)})`;
      return el('button', { type: 'button', class: 'la-clip', style: `flex-grow:${info.camera[n].dur}`, 'aria-label': `Play shot ${n + 1}: ${title}`,
        onclick: () => { touched = true; play(n); } }, pic, el('span', { class: 'la-mono' }, `0${n + 1} · ${title}`),
        el('em', { class: 'la-mono' }, `${(info.camera[n].dur / 1000).toFixed(1)} s`));
    }));
    const total = Math.round(shotSeconds());
    ruler.replaceChildren(...Array.from({ length: Math.floor(total / 3) + 1 }, (_, i) => el('span', {}, `00:${String(i * 3).padStart(2, '0')}`)));
    cutLabel.textContent = `The cut · Scene 0${current + 1} · ${info.title} · ${total} s`;
  }

  // What the slate's right column says for each shot: its price on the storyboard, how far its take has rendered,
  // then its length once the takes are in.
  function rowNotes(f) { [...rows.querySelectorAll('.la-shot')].forEach((b, n) => { b.lastChild.textContent = f(n); }); }

  // Cut to a scene. With the storyboard (the usual way), the sketch comes up over the old set and the new set is
  // built under it; without (calm motion), straight to its first shot.
  function cut(i) {
    if (i === current) return;
    current = i;
    const name = scenes.names[i], info = scenes.info(name);
    [, iso.textContent, wb.textContent] = READOUT[name];
    sceneName.textContent = `Scene 0${i + 1} · ${info.title}`;
    buttons.forEach((b, n) => b.setAttribute('aria-pressed', String(n === i)));
    type(`${info.shots[0]}. The same runner in every shot.`);
    drawShots(name);
    noise.scene(name);
    frame.classList.remove('taking'); take.pause();
    if (calm) { set.show(name); if (three) three.show(name); play(0); return; }
    board.innerHTML = scenes.svg(name, { sketch: true });
    board.style.clipPath = '';
    board.classList.add('on');
    frame.classList.remove('wiping');
    phase = 'board'; phaseAt = performance.now(); swapped = false;
    state.textContent = 'Storyboard';
    note.textContent = 'Nothing is made until you approve';
    approve.textContent = 'Approve · 180';
    approve.classList.remove('pressed');
    lens.textContent = info.camera[0].lens;
    move.classList.remove('on');
    rowNotes(() => '60 cr');
    rows.querySelectorAll('li').forEach((li) => li.classList.remove('on'));
  }

  function swap() {
    if (swapped) return;
    swapped = true;
    const name = scenes.names[current];
    set.show(name);
    if (three) three.show(name);
  }

  // Play shot n of the scene: a cut (a blink of black), then the camera's move over the shot's length.
  function play(n) {
    swap();
    board.classList.remove('on'); frame.classList.remove('wiping');
    phase = 'shots'; shot = n; phaseAt = performance.now();
    const c = camera()[n];
    set.shot(c, calm ? 0 : c.dur);
    if (three) three.shot(n, c.dur, phaseAt);
    lens.textContent = c.lens;
    moveName.textContent = `Shot 0${n + 1} · ${c.move}`;
    move.classList.toggle('on', !calm);
    state.textContent = `Take · shot 0${n + 1}`;
    note.textContent = `Cut together · ${Math.round(shotSeconds())} s`;
    approve.textContent = 'Approved';
    approve.classList.add('pressed');
    rowNotes((k) => `${(camera()[k].dur / 1000).toFixed(1)} s`);
    rows.querySelectorAll('li').forEach((li, k) => li.classList.toggle('on', k === n));
    clips.querySelectorAll('.la-clip').forEach((b, k) => b.classList.toggle('on', k === n));
    const clip = CLIPS[scenes.names[current]];
    if (clip && !calm) {
      if (!take.src.endsWith(clip)) take.src = clip;
      take.play().then(() => frame.classList.add('taking'), () => frame.classList.remove('taking'));
    }
    if (!calm) { flash.classList.remove('go'); void flash.offsetWidth; flash.classList.add('go'); }
  }

  // The 3D sets, loaded once the page has shown, where the browser can run them; the visitor can switch back.
  function pickMode(m, chosen) {
    if (m === '3d' && !three) return;
    mode = m;
    frame.classList.toggle('three', m === '3d');
    modeButtons.forEach((b, i) => b.setAttribute('aria-pressed', String((i === 0) === (m === '3d'))));
    if (chosen) { try { localStorage.setItem(SET_KEY, m); } catch (e) { /* storage off: the choice lasts this visit */ } }
  }
  if (canThree()) {
    setTimeout(() => import('./landing-3d.js').then((mod) => {
      if (!node.isConnected) return;
      three = mod.create(canvas);
      three.size(frame.clientWidth, frame.clientHeight);
      if (current >= 0) {
        three.show(scenes.names[current]);
        if (phase === 'shots') three.shot(shot, camera()[shot].dur, phaseAt);
      }
      modes.classList.remove('hidden');
      let saved = '';
      try { saved = localStorage.getItem(SET_KEY) || ''; } catch (e) { /* storage off */ }
      pickMode(saved === 'drawn' ? 'drawn' : '3d');
    }, () => { /* no 3D here: the drawn set stays */ }), 900);
  }

  // The monitor's clock: the timecode at 24 frames a second, the steps of a scene, the shot's progress, the level
  // bars and the 3D frame. It stops, and lets go of the 3D set and the sound, once the page is left.
  const started = performance.now();
  const tick = (now) => {
    if (!reel.isConnected && reel.dataset.placed) {
      if (three) three.dispose();
      noise.close();
      window.removeEventListener('scroll', onScroll); window.removeEventListener('resize', onResize);
      sized.disconnect();
      return;
    }
    if (reel.isConnected) reel.dataset.placed = '1';
    tc.textContent = frameTimecode(Math.floor((now - started) / (1000 / 24)) + 24 * 3600);
    const t = now - phaseAt;
    if (phase === 'board') {
      if (t > SWAP) swap();
      if (t > BOARD) { phase = 'approve'; phaseAt = now; approve.classList.add('pressed'); state.textContent = 'Approved'; }
    } else if (phase === 'approve') {
      if (t > APPROVE) { phase = 'render'; phaseAt = now; state.textContent = 'Rendering'; note.textContent = 'Approved · making the takes'; frame.classList.add('wiping'); }
    } else if (phase === 'render') {
      const q = Math.min(1, t / RENDER);
      const at = -12 + q * 124;   // the sketch's left edge, in % of the frame, slanted 12% across its height
      board.style.clipPath = `polygon(${at}% 0, 100% 0, 100% 100%, ${at - 12}% 100%)`;
      wipe.style.left = `${at - 6}%`;
      rowNotes((n) => { const done = Math.min(1, Math.max(0, q * 1.6 - n * 0.3)); return done >= 1 ? '✓' : `${Math.round(done * 100)}%`; });
      if (q >= 1) play(0);
    } else if (!calm) {
      const c = camera()[shot], p = Math.min(1, t / c.dur);
      moveBar.style.setProperty('--p', p.toFixed(3));
      const before = camera().slice(0, shot).reduce((n, k) => n + k.dur, 0);
      head.style.left = `${(((before + p * c.dur) / 1000 / shotSeconds()) * 100).toFixed(2)}%`;
      if (p >= 1) {
        if (shot < 2) play(shot + 1);
        else if (touched) play(0);
        else cut((current + 1) % scenes.names.length);
      }
    }
    if (noise.on) noise.levels(5).forEach((v, i) => { bars[i].style.transform = `scaleY(${(0.15 + v * 0.85).toFixed(2)})`; });
    if (three && mode === '3d' && !node.classList.contains('off') && !document.hidden) three.frame(now);
    requestAnimationFrame(tick);
  };

  // The reel: how far the page has scrolled through it folds the monitor into the corner (0 full, 1 folded).
  const live = () => !calm && window.innerWidth >= 900 && window.innerHeight >= 620;
  function onScroll() {
    if (!reel.classList.contains('live')) return;
    const span = reel.offsetHeight - window.innerHeight;
    const p = Math.min(1, Math.max(0, -reel.getBoundingClientRect().top / span));
    const e = p * p * (3 - 2 * p);
    const w = window.innerWidth, h = window.innerHeight;
    const to = Math.min(w * 0.46, 880) / w;   // the folded monitor's width, as a share of the screen
    const s = 1 + (to - 1) * e;
    node.style.transform = `translate(${((w - 92 - w * to) * e).toFixed(1)}px, ${(h * 0.11 * e).toFixed(1)}px) scale(${s.toFixed(4)})`;
    node.style.borderRadius = `${((14 * e) / s).toFixed(1)}px`;
    pin.style.setProperty('--reel', e.toFixed(3));
    pin.classList.toggle('folded', e > 0.4);   // the faded monitor's buttons stop taking clicks; the timeline's start
    const bar = reel.parentNode && reel.parentNode.querySelector('.la-bar-top');
    if (bar && e > 0) bar.classList.toggle('on', e > 0.55);
  }
  function onResize() {
    reel.classList.toggle('live', live());
    if (!reel.classList.contains('live')) { node.style.transform = node.style.borderRadius = ''; pin.style.removeProperty('--reel'); }
    onScroll();
  }
  const sized = new ResizeObserver(() => {
    set.resize();
    if (three) three.size(frame.clientWidth, frame.clientHeight);
  });
  sized.observe(frame);
  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onResize);
  onResize();

  // The 3D camera leans with the mouse too (the drawn planes read --px and --py, set in smooth()).
  node.addEventListener('pointermove', (e) => {
    if (!three || e.pointerType !== 'mouse') return;
    const box = node.getBoundingClientRect();
    three.pointer(((e.clientX - box.left) / box.width) * 2 - 1, ((e.clientY - box.top) / box.height) * 2 - 1);
  });
  node.addEventListener('pointerleave', () => { if (three) three.pointer(0, 0); });

  cut(0);
  requestAnimationFrame(tick);
  return reel;
}

// A row of a section's label: its number and name on the left, a note on the right.
const label = (left, right) => el('div', { class: 'la-label la-mono' }, el('span', {}, left), el('span', {}, right));

// The prompt a visitor typed before having an account. It waits in this browser and fills Home's prompt box after
// signing in (pages/home.js), so the first thing they see inside is their own shot, ready to make.
export const FIRST_PROMPT = 'scene.firstPrompt';
export function keepPrompt(text) {
  try { if (text && text.trim()) localStorage.setItem(FIRST_PROMPT, text.trim().slice(0, 2000)); } catch (e) { /* storage off: they type it again */ }
}

// The bar under the headline: the first shot, typed on the landing itself. start(text) takes it to an account.
function ask(start) {
  const input = el('input', { type: 'text', maxlength: 2000, 'aria-label': 'Describe your first shot',
    placeholder: 'A girl in a yellow raincoat on a rainy street at night' });
  return el('form', { class: 'la-ask', onsubmit: (e) => { e.preventDefault(); start(input.value || input.placeholder); } },
    input, el('button', { type: 'submit', class: 'la-btn solid' }, 'Make this'));
}

export function renderLanding(root, { signupOpen }) {
  // A new button for each place it appears: one element can only stand in one place on the page.
  const join = (cls = '') => (signupOpen
    ? el('a', { class: 'la-btn ' + cls, href: '/signup' }, 'Create an account')
    : el('a', { class: 'la-btn ' + cls, href: '/signin' }, 'Sign in'));
  const signIn = (cls = '') => el('a', { class: 'la-btn ' + cls, href: '/signin' }, 'Sign in');
  const start = (text) => { keepPrompt(text); go(signupOpen ? '/signup' : '/signin'); };

  const page = el('div', { class: 'la' }, monitor(join, signupOpen, start), ...sections(join, signIn, signupOpen, start));
  root.replaceChildren(page);
  window.scrollTo(0, 0);
  smooth(page);
}

// What makes the long page feel like one shot: sections rise in as they come into view, the bar with the doors slides
// down once the first screen is passed, and the monitor's moving parts rest while it is out of sight. With the Motion
// setting on calm, or the system asking for less motion, everything simply stands in place.
export function smooth(page) {
  const calm = still() || matchMedia('(prefers-reduced-motion: reduce)').matches;
  const monitorNode = page.querySelector('.la-monitor');
  const bar = page.querySelector('.la-bar-top');
  if (!calm) {
    page.classList.add('la-anim');
    const seen = new IntersectionObserver((entries) => entries.forEach((e) => {
      if (e.isIntersecting) { e.target.classList.add('in'); seen.unobserve(e.target); }
    }), { rootMargin: '0px 0px -8% 0px', threshold: 0.12 });
    page.querySelectorAll('.la-rv').forEach((n) => seen.observe(n));
  }
  if (monitorNode && !calm) {
    // Depth: the scene's layers lean away from the pointer, nearer ones more (the CSS reads --px and --py).
    let raf = 0;
    monitorNode.addEventListener('pointermove', (e) => {
      if (e.pointerType !== 'mouse' || raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        const box = monitorNode.getBoundingClientRect();
        monitorNode.style.setProperty('--px', (((e.clientX - box.left) / box.width) * 2 - 1).toFixed(3));
        monitorNode.style.setProperty('--py', (((e.clientY - box.top) / box.height) * 2 - 1).toFixed(3));
      });
    });
    monitorNode.addEventListener('pointerleave', () => { monitorNode.style.setProperty('--px', 0); monitorNode.style.setProperty('--py', 0); });
  }
  // The cue scrolls on to what comes next: through the reel to the shots laid out (the landing), or to the first section.
  const next = page.querySelector('.la-manifesto');
  if (monitorNode && next) {
    const onward = () => {
      const reel = page.querySelector('.la-reel.live');
      if (reel) window.scrollTo({ top: reel.offsetTop + reel.offsetHeight - window.innerHeight, behavior: calm ? 'auto' : 'smooth' });
      else next.scrollIntoView({ behavior: calm ? 'auto' : 'smooth' });
    };
    (monitorNode.querySelector('.la-chrome') || monitorNode).append(el('button', { type: 'button', class: 'la-cue la-mono', onclick: onward }, 'Scroll', el('i')));
  }
  if (monitorNode) {
    new IntersectionObserver(([e]) => {
      monitorNode.classList.toggle('off', !e.isIntersecting);
      if (bar) bar.classList.toggle('on', e.intersectionRatio < 0.25);
    }, { threshold: [0, 0.25] }).observe(monitorNode);
  }
}

// The landing below its monitor, from Why down to the footer. The sign-in pages show it under their form too; join,
// signIn and start make the buttons and take a prompt, so there they lead back up to the form.
export function sections(join, signIn, signupOpen, start) {
  const rv = (n, i = 0) => { n.classList.add('la-rv'); if (i) n.style.setProperty('--d', `${i * 70}ms`); return n; };

  const takes = el('div', { class: 'la-strip' }, TAKES.map(([scene, take, length, note, look], i) => rv(el('div', { class: 'la-take ' + look },
    picture(scene, 'la-pic'),
    el('dl', {}, el('dt', {}, 'Shot'), el('dd', {}, `01 · ${take}`), el('dt', {}, 'Model'), el('dd', {}, 'MiniMax H3'),
      el('dt', {}, 'Length'), el('dd', {}, length), el('dt', {}, 'Note'), el('dd', {}, note))), i)));

  const plan = el('div', { class: 'la-screen', 'aria-hidden': 'true' },
    el('div', { class: 'la-bar la-mono' }, el('span', {}, 'Agent 1'), el('span', {}, 'Plans first')),
    el('div', { class: 'la-you' }, 'A 20 second ad for our sneaker drop. Rooftop, golden hour, the same runner in every shot.'),
    el('div', { class: 'la-plan' },
      el('header', {}, el('b', {}, 'Plan · 3 shots'), el('span', {}, 'Nothing is made until you approve')),
      scenes.info('rooftop').shots.map((shot) => el('div', { class: 'la-row' }, picture('rooftop', 'la-thumb'), el('span', {}, shot), el('em', {}, '60 cr'))),
      el('footer', {}, el('span', { class: 'la-mono' }, 'Storyboard first'), el('span', { class: 'la-btn solid small' }, 'Approve · 180'))));

  const uses = el('div', { class: 'la-uses' }, USES.map(([scene, title, prompt, sketch], i) => rv(el('button', { type: 'button', class: 'la-use',
    title: 'Start with this prompt', onclick: () => start(prompt) },
    picture(scene, 'la-pic', !!sketch),
    el('span', { class: 'la-use-body' },
      el('b', {}, title),
      el('span', { class: 'la-use-prompt' }, `“${prompt}”`),
      el('span', { class: 'la-use-go la-mono' }, 'Start with this →'))), i % 4)));

  // NeuralCore as the panel shows it: the cast, places and voices kept once, and the agent's notes.
  const core = el('div', { class: 'la-screen la-core', 'aria-hidden': 'true' },
    el('div', { class: 'la-bar la-mono' }, el('span', {}, 'NeuralCore'), el('span', {}, 'Monsoon ad · Module 1')),
    [['Cast', [['rooftop', 'Meera', 'Yellow raincoat · in 14 shots'], ['neon', 'Raghav', 'Denim jacket · in 6 shots']]],
      ['Places', [['neon', 'Night market', 'Wet street, neon signs'], ['rooftop', 'Rooftop', 'Golden hour, skyline']]],
      ['Voices', [['deep', 'Meera · warm', 'Hindi and English']]]].map(([group, items]) => el('div', { class: 'la-core-group' },
      el('span', { class: 'la-mono' }, group),
      items.map(([scene, name, note]) => el('div', { class: 'la-core-item' }, picture(scene, 'la-core-pic'), el('b', {}, name), el('span', {}, note))))),
    el('div', { class: 'la-core-note' }, el('span', { class: 'la-mono' }, 'Note'), 'Meera never takes the raincoat off. Keep the red umbrella in her left hand.'));

  // The bar with the doors, fixed at the top once the first screen is scrolled past (smooth() turns it on).
  const bar = el('div', { class: 'la-bar-top' },
    el('a', { class: 'la-brand', href: '/' }, el('img', { src: '/assets/img/logo.svg?v=clapper', alt: '' }), 'Scene.ai'),
    el('nav', { class: 'la-doors' }, signupOpen && signIn('quiet small'), join('solid small')));

  return [
    bar,

    el('section', { class: 'la-wrap la-manifesto' },
      label('01 · Why', 'Scene.ai'),
      rv(el('p', {}, 'Most AI video tools give you a slot machine. ', el('em', {}, 'Scene.ai gives you a set:'),
        ' a cast that stays the same, takes you can keep or roll again, and a cut you can trust.'))),

    el('section', { class: 'la-wrap la-use-sec' },
      label('02 · What you can make', 'Pick one to start'),
      rv(el('h2', {}, 'Start from a shot, a script or an idea.')),
      uses),

    el('section', { class: 'la-wrap la-report' },
      label('03 · The take report', 'Shot 1 · Rooftop at dusk'),
      takes,
      el('div', { class: 'la-steps' }, STEPS.map(([title, text], i) => rv(el('div', {}, el('b', { class: 'la-mono' }, `0${i + 1}`), el('h3', {}, title), el('p', {}, text)), i)))),

    el('section', { class: 'la-wrap la-agent' },
      label('04 · The agent', 'Plans first, makes later'),
      el('div', { class: 'la-split' },
        rv(el('div', {},
          el('h2', {}, 'An assistant director that asks before it spends.'),
          el('p', {}, 'Tell it what you are making, in plain words. It plans the shots, prices them and waits for your nod; then it looks at every take and offers a retake when a face or a place is wrong.'),
          el('ul', { class: 'la-chips' }, AGENT.map((t) => el('li', {}, t))),
          el('p', { class: 'la-note la-mono' }, 'The agent is open to invited accounts for now.'))),
        rv(plan, 1))),

    el('section', { class: 'la-wrap la-memory' },
      label('05 · NeuralCore', 'The studio remembers'),
      el('div', { class: 'la-split' },
        rv(core),
        rv(el('div', {},
          el('h2', {}, 'Shot 1 and shot 40. The same Meera.'),
          el('p', {}, 'Say “keep her as Meera” once. Her face, her raincoat, the street and her voice are kept in the project, and every later shot of her uses them.'),
          el('p', {}, 'Come back next week and the set is as you left it: the cast, the places, the notes, and what you liked and did not.')), 1))),

    el('section', { class: 'la-wrap la-bench' },
      label('06 · After the take', 'The rest of the studio'),
      rv(el('h2', {}, 'From a take to a finished film.')),
      el('div', { class: 'la-bento' }, BENCH.map(([tag, title, text], i) => rv(el('div', { class: 'la-tile' },
        el('span', { class: 'la-mono' }, tag), el('h3', {}, title), el('p', {}, text)), i % 3)))),

    el('section', { class: 'la-wrap la-kit' },
      label('07 · On the cart', 'The models'),
      rv(el('h2', {}, 'Everything on the cart.')),
      el('table', {}, el('tbody', {}, KIT.map(([kind, what, model, text]) => rv(el('tr', {},
        el('td', { class: 'la-mono' }, kind), el('th', { scope: 'row' }, what), el('td', { class: 'la-model' }, model), el('td', {}, text))))))),

    el('section', { class: 'la-wrap la-price' },
      label('08 · Credits', 'Pay for what you make'),
      el('div', { class: 'la-split' },
        rv(el('h2', {}, 'You pay for the take, not the render time.')),
        rv(el('div', {},
          el('p', {}, 'A flat price for a picture, a price per second for video and music. You see it before you press Generate.'),
          el('ul', { class: 'la-chips' }, ['Price shown first', 'Failed jobs refunded', 'Edits and titles free'].map((t) => el('li', {}, t)))), 1))),

    el('section', { class: 'la-wrap la-faq' },
      label('09 · Questions', 'Before you start'),
      el('div', {}, FAQ.map(([q, a]) => rv(el('details', {}, el('summary', {}, q), el('p', {}, a)))))),

    el('section', { class: 'la-cut' },
      rv(el('h2', {}, 'CUT.')),
      el('p', {}, signupOpen ? 'Your first scene is a sentence away.' : 'Welcome back. The set is as you left it.'),
      el('div', { class: 'la-doors center' }, join('solid big'), signupOpen && signIn('big'))),

    el('footer', { class: 'la-end la-mono' }, el('span', {}, 'Scene.ai'), el('span', {}, 'A studio for video, pictures and music'))];
}
