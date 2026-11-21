// The monitor's director. How a scene is made, as the studio makes one: the storyboard first while the plan types
// itself, then Approve, then the takes render (the colour wipes across the sketch), then the three shots play, each a
// camera move. Runs on its own clock: what changes every frame (the timecode, the wipe, the playhead, the level bars)
// goes straight to its element; the rest is the view, which React draws.

import { useLayoutEffect, useRef, useState, type RefObject } from 'react';
import * as scenes from '../../../common/landing/landingScenes';
import { READOUT, calmNow, frameTimecode } from '../../../common/landing/words';
import { prefs } from '../../../common/prefs';
import type { DrawnHandle } from './DrawnSet';
import type { Three } from './landing3d';
import { sound } from './landingSound';

const BOARD = 2800,
  APPROVE = 500,
  RENDER = 1700,
  SWAP = 650; // ms; the set changes under the sketch at SWAP
// A real take of each scene made by the studio, to play over the drawn set while its shots run: scene name → its
// address under /assets/landing/. None has been made yet; the drawn and 3D sets stand in.
const CLIPS: Record<string, string> = {};
const SET_KEY = 'scene.landingSet'; // '3d' or 'drawn', when the visitor picked one

export type Mode = '3d' | 'drawn';
export type Stage = {
  monitor: RefObject<HTMLElement | null>;
  frame: RefObject<HTMLDivElement | null>;
  set: RefObject<DrawnHandle | null>;
  canvas: RefObject<HTMLCanvasElement | null>;
  take: RefObject<HTMLVideoElement | null>;
  board: RefObject<HTMLDivElement | null>;
  wipe: RefObject<HTMLElement | null>;
  tc: RefObject<HTMLSpanElement | null>;
  typed: RefObject<HTMLDivElement | null>;
  moveBar: RefObject<HTMLElement | null>;
  head: RefObject<HTMLElement | null>;
  bars: RefObject<(HTMLElement | null)[]>;
  resting: RefObject<boolean>;
};

const COST = ['60 cr', '60 cr', '60 cr'];
const FIRST = {
  scene: 0,
  sceneOn: false,
  status: '',
  note: '',
  approve: '',
  pressed: false,
  lens: '',
  iso: '',
  wb: '',
  moveName: '',
  moveOn: false,
  sketch: '',
  boardOn: false,
  wiping: false,
  taking: false,
  notes: COST,
  shot: null as number | null,
  flash: 0,
  mode: 'drawn' as Mode,
  three: false,
  sound: false,
};
export type View = typeof FIRST;
type Engine = {
  pickScene: (i: number) => void;
  playShot: (n: number) => void;
  pickMode: (m: Mode) => void;
  toggleSound: () => void;
};

// Can this browser show the 3D sets? WebGL, the full motion setting and a screen wide enough for the monitor.
function canThree() {
  if (calmNow() || window.innerWidth < 900) return false;
  try {
    return !!document.createElement('canvas').getContext('webgl2');
  } catch {
    return false;
  }
}

export function useDirector(stage: Stage) {
  const [view, setView] = useState(FIRST);
  const engine = useRef<Engine | null>(null);

  useLayoutEffect(() => {
    const calm = calmNow();
    const patch = (changes: Partial<View>) => setView((was) => ({ ...was, ...changes }));
    const noise = sound();
    let current = -1,
      phase: 'board' | 'approve' | 'render' | 'shots' = 'shots',
      shot = 0,
      phaseAt = 0,
      swapped = true,
      touched = false,
      flashes = 0,
      mode: Mode = 'drawn',
      three: Three | null = null,
      notes = COST,
      gone = false,
      raf = 0;
    let typing: ReturnType<typeof setInterval> | undefined;
    const name = () => scenes.names[current];
    const camera = () => scenes.info(name()).camera;
    const shotSeconds = () => camera().reduce((n, c) => n + c.dur, 0) / 1000;

    function type(text: string) {
      clearInterval(typing);
      if (calm) {
        if (stage.typed.current) stage.typed.current.textContent = text;
        return;
      }
      let n = 0;
      typing = setInterval(() => {
        n += 1;
        if (stage.typed.current) stage.typed.current.textContent = text.slice(0, n);
        if (n >= text.length) clearInterval(typing);
      }, 32);
    }

    // What the slate's right column says for each shot: its price on the storyboard, how far its take has rendered,
    // then its length once the takes are in.
    function rowNotes(f: (n: number) => string) {
      const next = [0, 1, 2].map(f);
      if (next.join() === notes.join()) return;
      notes = next;
      patch({ notes });
    }

    // Cut to a scene. With the storyboard (the usual way), the sketch comes up over the old set and the new set is
    // built under it; without (calm motion), straight to its first shot.
    function cut(i: number) {
      if (i === current) return;
      current = i;
      const info = scenes.info(name());
      const [, iso, wb] = READOUT[name()];
      notes = COST;
      patch({ scene: i, sceneOn: true, iso, wb, taking: false, shot: null, notes });
      type(`${info.shots[0]}. The same runner in every shot.`);
      noise.scene(name());
      stage.take.current?.pause();
      if (calm) {
        stage.set.current?.show(name());
        three?.show(name());
        play(0);
        return;
      }
      if (stage.board.current) stage.board.current.style.clipPath = '';
      phase = 'board';
      phaseAt = performance.now();
      swapped = false;
      patch({
        sketch: scenes.svg(name(), { sketch: true }),
        boardOn: true,
        wiping: false,
        status: 'Storyboard',
        note: 'Nothing is made until you approve',
        approve: 'Approve · 180',
        pressed: false,
        lens: info.camera[0].lens,
        moveOn: false,
      });
    }

    function swap() {
      if (swapped) return;
      swapped = true;
      stage.set.current?.show(name());
      three?.show(name());
    }

    // Play shot n of the scene: a cut (a blink of black), then the camera's move over the shot's length.
    function play(n: number) {
      swap();
      phase = 'shots';
      shot = n;
      phaseAt = performance.now();
      const c = camera()[n];
      stage.set.current?.shot(c, calm ? 0 : c.dur);
      three?.shot(n, c.dur, phaseAt);
      if (!calm) flashes += 1;
      patch({
        boardOn: false,
        wiping: false,
        lens: c.lens,
        moveName: `Shot 0${n + 1} · ${c.move}`,
        moveOn: !calm,
        status: `Take · shot 0${n + 1}`,
        note: `Cut together · ${Math.round(shotSeconds())} s`,
        approve: 'Approved',
        pressed: true,
        shot: n,
        flash: flashes,
      });
      rowNotes((k) => `${(camera()[k].dur / 1000).toFixed(1)} s`);
      const clip = CLIPS[name()];
      const take = stage.take.current;
      if (clip && !calm && take) {
        if (!take.src.endsWith(clip)) take.src = clip;
        take.play().then(
          () => patch({ taking: true }),
          () => patch({ taking: false }),
        );
      }
    }

    // The 3D sets, loaded once the page has shown, where the browser can run them; the visitor can switch back.
    function pickMode(m: Mode, chosen = false) {
      if (m === '3d' && !three) return;
      mode = m;
      patch({ mode: m });
      if (chosen) prefs.set(SET_KEY, m); // storage off: the choice lasts this visit
    }
    const size = () => three?.size(stage.frame.current?.clientWidth ?? 0, stage.frame.current?.clientHeight ?? 0);
    const threeTimer = canThree()
      ? setTimeout(() => {
          import('./landing3d').then(
            (mod) => {
              if (gone || !stage.canvas.current) return;
              three = mod.create(stage.canvas.current);
              size();
              if (current >= 0) {
                three.show(name());
                if (phase === 'shots') three.shot(shot, camera()[shot].dur, phaseAt);
              }
              patch({ three: true });
              pickMode(prefs.get(SET_KEY) === 'drawn' ? 'drawn' : '3d');
            },
            () => {
              /* no 3D here: the drawn set stays */
            },
          );
        }, 900)
      : undefined;

    // The monitor's clock: the timecode at 24 frames a second, the steps of a scene, the shot's progress, the level
    // bars and the 3D frame.
    const started = performance.now();
    const tick = (now: number) => {
      if (stage.tc.current)
        stage.tc.current.textContent = frameTimecode(Math.floor((now - started) / (1000 / 24)) + 24 * 3600);
      const t = now - phaseAt;
      if (phase === 'board') {
        if (t > SWAP) swap();
        if (t > BOARD) {
          phase = 'approve';
          phaseAt = now;
          patch({ pressed: true, status: 'Approved' });
        }
      } else if (phase === 'approve') {
        if (t > APPROVE) {
          phase = 'render';
          phaseAt = now;
          patch({ status: 'Rendering', note: 'Approved · making the takes', wiping: true });
        }
      } else if (phase === 'render') {
        const q = Math.min(1, t / RENDER);
        const at = -12 + q * 124; // the sketch's left edge, in % of the frame, slanted 12% across its height
        if (stage.board.current)
          stage.board.current.style.clipPath = `polygon(${at}% 0, 100% 0, 100% 100%, ${at - 12}% 100%)`;
        if (stage.wipe.current) stage.wipe.current.style.left = `${at - 6}%`;
        rowNotes((n) => {
          const done = Math.min(1, Math.max(0, q * 1.6 - n * 0.3));
          return done >= 1 ? '✓' : `${Math.round(done * 100)}%`;
        });
        if (q >= 1) play(0);
      } else if (!calm) {
        const c = camera()[shot],
          p = Math.min(1, t / c.dur);
        stage.moveBar.current?.style.setProperty('--p', p.toFixed(3));
        const before = camera()
          .slice(0, shot)
          .reduce((n, k) => n + k.dur, 0);
        if (stage.head.current)
          stage.head.current.style.left = `${(((before + p * c.dur) / 1000 / shotSeconds()) * 100).toFixed(2)}%`;
        if (p >= 1) {
          if (shot < 2) play(shot + 1);
          else if (touched) play(0);
          else cut((current + 1) % scenes.names.length);
        }
      }
      if (noise.on)
        noise.levels(5).forEach((v, i) => {
          const bar = stage.bars.current[i];
          if (bar) bar.style.transform = `scaleY(${(0.15 + v * 0.85).toFixed(2)})`;
        });
      if (three && mode === '3d' && !stage.resting.current && !document.hidden) three.frame(now);
      raf = requestAnimationFrame(tick);
    };

    const sized = new ResizeObserver(() => {
      stage.set.current?.resize();
      size();
    });
    if (stage.frame.current) sized.observe(stage.frame.current);

    // The 3D camera leans with the mouse too (the drawn planes read --px and --py, set in useMonitorLife).
    const monitor = stage.monitor.current;
    const lean = (e: PointerEvent) => {
      if (!three || e.pointerType !== 'mouse' || !monitor) return;
      const box = monitor.getBoundingClientRect();
      three.pointer(((e.clientX - box.left) / box.width) * 2 - 1, ((e.clientY - box.top) / box.height) * 2 - 1);
    };
    const straighten = () => three?.pointer(0, 0);
    monitor?.addEventListener('pointermove', lean);
    monitor?.addEventListener('pointerleave', straighten);

    engine.current = {
      pickScene(i) {
        touched = true;
        cut(i);
      },
      playShot(n) {
        touched = true;
        play(n);
      },
      pickMode: (m) => pickMode(m, true),
      toggleSound() {
        if (noise.on) noise.stop();
        else noise.start(name());
        patch({ sound: noise.on });
      },
    };
    raf = requestAnimationFrame((now) => {
      cut(0);
      tick(now);
    });

    // Once the page is left it stops, and lets go of the 3D set and the sound.
    return () => {
      gone = true;
      engine.current = null;
      cancelAnimationFrame(raf);
      clearInterval(typing);
      clearTimeout(threeTimer);
      sized.disconnect();
      monitor?.removeEventListener('pointermove', lean);
      monitor?.removeEventListener('pointerleave', straighten);
      three?.dispose();
      noise.close();
    };
  }, [stage]);

  return { view, engine };
}
