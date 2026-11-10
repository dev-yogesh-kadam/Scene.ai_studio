// The first screen of the landing page is a camera monitor on the set: the frame is a scene, with frame lines, a
// timecode that runs, the lens and light readouts, and a slate where the plan of the shot types itself. The shot rows
// play a shot, the scene buttons cut the whole set, and the set has its sound. Scrolling folds the monitor away and
// lays its shots out on a timeline (the reel).

import { useEffect, useMemo, useRef, type ReactNode } from 'react';
import { Cue, useMonitorLife, useSetBar } from '../../../common/landing/LandingRoot';
import * as scenes from '../../../common/landing/landingScenes';
import { Picture } from '../../../common/landing/Picture';
import { SvgDrawing } from '../../../common/components/SvgDrawing';
import type { DrawnHandle } from './DrawnSet';
import { DrawnSet } from './DrawnSet';
import type { Door } from './Sections';
import { useDirector, type Stage } from './useDirector';
import { useReel } from './useReel';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared.module.css';
import css1 from '../../../common/components/Shared2.module.css';
import css2 from '../../../common/components/Shared3.module.css';
import css3 from '../../../common/components/Shared4.module.css';
import css4 from '../../../common/landing/Landing.module.css';
import css5 from '../../../common/landing/Landing2.module.css';
import css6 from '../../../common/landing/Landing3.module.css';
import css7 from '../../../common/landing/Landing4.module.css';
import css8 from '../../../common/landing/Landing5.module.css';
import css9 from '../../../common/landing/Landing6.module.css';
import css10 from '../../../common/landing/Landing7.module.css';
import css11 from '../../../common/landing/Landing8.module.css';
import css12 from '../guide/GuidePage.module.css';
import css13 from './Monitor.module.css';
import css14 from './Sections.module.css';
import css15 from './Shared.module.css';
const css = classesOf(
  css0,
  css1,
  css2,
  css3,
  css4,
  css5,
  css6,
  css7,
  css8,
  css9,
  css10,
  css11,
  css12,
  css13,
  css14,
  css15,
);

const WAVE = Array.from(
  { length: 140 },
  (_, i) => `${(18 + Math.abs(Math.sin(i * 0.37) * 52 + Math.sin(i * 1.7) * 18)).toFixed(0)}%`,
);

/** The bar under the headline: the first shot, typed on the landing itself. */
function Ask({ start }: { start: (text: string) => void }) {
  const placeholder = 'A girl in a yellow raincoat on a rainy street at night';
  const input = useRef<HTMLInputElement>(null);
  return (
    <form
      className={css('la-ask')}
      onSubmit={(e) => {
        e.preventDefault();
        start(input.current?.value || placeholder);
      }}
    >
      <input ref={input} type="text" maxLength={2000} aria-label="Describe your first shot" placeholder={placeholder} />
      <button type="submit" className={css('la-btn solid')}>
        Make this
      </button>
    </form>
  );
}

export function Monitor({
  join,
  signupOpen,
  start,
}: {
  join: Door;
  signupOpen: boolean;
  start: (text: string) => void;
}) {
  const reel = useRef<HTMLDivElement>(null);
  const pin = useRef<HTMLDivElement>(null);
  const monitor = useRef<HTMLElement>(null);
  const frame = useRef<HTMLDivElement>(null);
  const set = useRef<DrawnHandle>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const take = useRef<HTMLVideoElement>(null);
  const board = useRef<HTMLDivElement>(null);
  const wipe = useRef<HTMLElement>(null);
  const tc = useRef<HTMLSpanElement>(null);
  const typed = useRef<HTMLDivElement>(null);
  const moveBar = useRef<HTMLElement>(null);
  const head = useRef<HTMLElement>(null);
  const bars = useRef<(HTMLElement | null)[]>([]);
  const resting = useRef(false);
  const stage = useMemo<Stage>(
    () => ({ monitor, frame, set, canvas, take, board, wipe, tc, typed, moveBar, head, bars, resting }),
    [],
  );
  const { view, engine } = useDirector(stage);
  const off = useMonitorLife(monitor);
  const setBar = useSetBar();
  const { live, folded } = useReel(reel, pin, monitor, setBar);
  useEffect(() => {
    resting.current = off;
  }, [off]);

  const name = scenes.names[view.scene];
  const info = scenes.info(name);
  const total = Math.round(info.camera.reduce((n, c) => n + c.dur, 0) / 1000);
  const shotLabel = (n: number, title: string) => `Play shot ${n + 1}: ${title}`;
  const reelEnd = () =>
    live && reel.current ? reel.current.offsetTop + reel.current.offsetHeight - window.innerHeight : null;
  const doors: ReactNode = (
    <nav className={css('la-doors')}>
      {signupOpen && (
        <a className={css('la-btn quiet')} href="/signin">
          Sign in
        </a>
      )}
      {join('solid')}
    </nav>
  );

  return (
    <div ref={reel} className={css('la-reel' + (live ? ' live' : ''))}>
      <div ref={pin} className={css('la-reel-pin' + (folded ? ' folded' : ''))}>
        <section ref={monitor} className={css('la-monitor' + (off ? ' off' : ''))}>
          <div
            ref={frame}
            className={css(
              ['la-set', view.taking && 'taking', view.wiping && 'wiping', view.mode === '3d' && 'three']
                .filter(Boolean)
                .join(' '),
            )}
          >
            <DrawnSet ref={set} />
            <canvas ref={canvas} className={css('la-3d')} aria-hidden="true" />
            <video ref={take} className={css('la-real')} muted loop playsInline />
            <SvgDrawing ref={board} svg={view.sketch} className={css('la-board' + (view.boardOn ? ' on' : ''))} />
            <i ref={wipe} className={css('la-wipe')} aria-hidden="true" />
            <i key={view.flash} className={css('la-flash' + (view.flash ? ' go' : ''))} aria-hidden="true" />
          </div>
          <div className={css('la-grade')} />
          <div className={css('la-grain')} />
          <div className={css('la-chrome')}>
            <div className={css('la-hud')} aria-hidden="true">
              {['tl', 'tr', 'bl', 'br'].map((c) => (
                <i key={c} className={css('la-corner la-' + c)} />
              ))}
              <div className={css('la-thirds')} />
              <div className={css('la-cross')} />
            </div>
            <header className={css('la-top')}>
              <a className={css('la-brand')} href="/">
                <img src="/img/logo.svg?v=clapper" alt="" />
                Scene.ai
              </a>
              <div className={css('la-readout la-mono')} aria-hidden="true">
                <span ref={tc} className={css('la-rec')} data-testid="timecode">
                  01:00:00:00
                </span>
                <span>{view.lens}</span>
                <span>{view.iso}</span>
                <span>{view.wb}</span>
              </div>
              {doors}
            </header>
            <div className={css('la-move la-mono' + (view.moveOn ? ' on' : ''))} aria-hidden="true">
              <b>{view.moveName}</b>
              <i ref={moveBar} />
            </div>
            <div className={css('la-lower')}>
              <div>
                <h1>
                  Direct
                  <br />
                  your <b>scene.</b>
                </h1>
                <p className={css('la-sub')}>
                  Write the shot. The studio makes the takes, keeps the same faces from shot to shot, and cuts them
                  together, without a node graph in sight.
                </p>
                <Ask start={start} />
              </div>
              <div className={css('la-slate')}>
                <header className={css('la-mono')} aria-hidden="true">
                  <span>{view.sceneOn ? `Scene 0${view.scene + 1} · ${info.title}` : ''}</span>
                  <span>{view.status}</span>
                </header>
                <div ref={typed} className={css('la-typed')} aria-hidden="true" />
                <ol>
                  {info.shots.map((title, n) => (
                    <li key={title} className={css(view.shot === n ? 'on' : undefined)}>
                      <button
                        type="button"
                        className={css('la-shot')}
                        title={shotLabel(n, title)}
                        onClick={() => engine.current?.playShot(n)}
                      >
                        <span>{`0${n + 1}`}</span>
                        <span>{title}</span>
                        <span>{view.notes[n]}</span>
                      </button>
                    </li>
                  ))}
                </ol>
                <footer aria-hidden="true">
                  <span className={css('la-mono')}>{view.note}</span>
                  <span className={css('la-btn solid small' + (view.pressed ? ' pressed' : ''))}>{view.approve}</span>
                </footer>
              </div>
            </div>
            <div className={css('la-scenes')} role="group" aria-label="Scene">
              <span className={css('la-mono')}>Scene</span>
              {scenes.names.map((scene, i) => (
                <button
                  key={scene}
                  type="button"
                  aria-pressed={view.sceneOn && i === view.scene}
                  onClick={() => engine.current?.pickScene(i)}
                >
                  {`${i + 1} · ${scenes.info(scene).title}`}
                </button>
              ))}
              <span className={css('la-modes' + (view.three ? '' : ' hidden'))} role="group" aria-label="Set">
                <span className={css('la-mono')}>Set</span>
                <button type="button" aria-pressed={view.mode === '3d'} onClick={() => engine.current?.pickMode('3d')}>
                  3D
                </button>
                <button
                  type="button"
                  aria-pressed={view.mode === 'drawn'}
                  onClick={() => engine.current?.pickMode('drawn')}
                >
                  Drawn
                </button>
              </span>
            </div>
            <button
              type="button"
              className={css('la-sound la-mono')}
              aria-pressed={view.sound}
              title="The sound of the set"
              onClick={() => engine.current?.toggleSound()}
            >
              <span aria-hidden="true">
                {[0, 1, 2, 3, 4].map((i) => (
                  <i
                    key={i}
                    ref={(n) => {
                      bars.current[i] = n;
                    }}
                  />
                ))}
              </span>
              <span>{view.sound ? 'Sound on' : 'Sound off'}</span>
            </button>
            <Cue reelEnd={reelEnd} />
          </div>
        </section>
        <div className={css('la-cutline')}>
          <div className={css('la-cut-copy')}>
            <div className={css('la-mono la-cut-label')}>
              <span>{`The cut · Scene 0${view.scene + 1} · ${info.title} · ${total} s`}</span>
            </div>
            <h2>
              One prompt.
              <br />
              <b>Three shots, one cut.</b>
            </h2>
            <p>
              The scene above was planned as these three shots: each one a camera move on the same set, with the same
              runner, cut together with sound. Pick a shot to play it.
            </p>
          </div>
          <div className={css('la-track')}>
            <div className={css('la-ruler la-mono')} aria-hidden="true">
              {Array.from({ length: Math.floor(total / 3) + 1 }, (_, i) => (
                <span key={i}>{`00:${String(i * 3).padStart(2, '0')}`}</span>
              ))}
            </div>
            <div className={css('la-lanes')}>
              <div className={css('la-clips')}>
                {info.shots.map((title, n) => {
                  const c = info.camera[n].to;
                  return (
                    <button
                      key={name + title}
                      type="button"
                      className={css('la-clip' + (view.shot === n ? ' on' : ''))}
                      style={{ flexGrow: info.camera[n].dur }}
                      aria-label={shotLabel(n, title)}
                      onClick={() => engine.current?.playShot(n)}
                    >
                      <Picture
                        name={name}
                        className={css('la-clip-pic')}
                        style={{
                          transformOrigin: `${(c.fx / 16).toFixed(1)}% ${(c.fy / 9).toFixed(1)}%`,
                          transform: `scale(${c.k.toFixed(2)})`,
                        }}
                      />
                      <span className={css('la-mono')}>{`0${n + 1} · ${title}`}</span>
                      <em className={css('la-mono')}>{`${(info.camera[n].dur / 1000).toFixed(1)} s`}</em>
                    </button>
                  );
                })}
              </div>
              <div className={css('la-wave')} aria-hidden="true">
                {WAVE.map((height, i) => (
                  <i key={i} style={{ height }} />
                ))}
              </div>
              <i ref={head} className={css('la-head')} aria-hidden="true" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
