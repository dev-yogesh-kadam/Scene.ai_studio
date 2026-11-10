// The sign-in pages are the landing page's monitor held on one scene: its frame lines, the camera's readouts and a
// running timecode, the headline at the lower left and, where the landing has the slate, the form. The admin console's
// sign-in is drawn with it too; the studio's has the landing's sections below.

import { useEffect, useRef, type ReactNode } from 'react';
import { Link } from 'react-router';
import { Cue, LandingRoot, useMonitorLife } from './LandingRoot';
import { Picture } from './Picture';
import { READOUT, frameTimecode } from './words';
import { classesOf } from '../cx';
import css0 from '../components/Shared3.module.css';
import css1 from './Landing.module.css';
import css2 from './Landing2.module.css';
import css3 from './Landing3.module.css';
import css4 from './Landing4.module.css';
import css5 from './Landing5.module.css';
import css6 from './Landing6.module.css';
import css7 from './Landing7.module.css';
import css8 from './Landing8.module.css';
import css9 from './landingScenes.module.css';
import css10 from '../../studio/pages/landing/Monitor.module.css';
import css11 from '../../studio/pages/landing/Sections.module.css';
const css = classesOf(css0, css1, css2, css3, css4, css5, css6, css7, css8, css9, css10, css11);

export function SignInSet({
  scene,
  home,
  heading,
  sub,
  points,
  tag,
  children,
  below,
}: {
  scene: string;
  home?: string; // where the brand leads (the landing); none on the console
  heading: ReactNode;
  sub: string;
  points: string[];
  tag: string;
  children: ReactNode; // the slate's card: the form
  below?: ReactNode;
}) {
  const brand = (
    <>
      <img src="/img/logo.svg?v=clapper" alt="" />
      Scene.ai
    </>
  );
  return (
    <LandingRoot className={css('auth-set')} moving={!!below}>
      <SetMonitor withSections={!!below}>
        <Picture name={scene} className={css('la-frame')} testId="scene" />
        <div className={css('la-grade')} />
        <div className={css('la-grain')} />
        <div className={css('la-hud')} aria-hidden="true">
          {['tl', 'tr', 'bl', 'br'].map((c) => (
            <i key={c} className={css('la-corner la-' + c)} />
          ))}
          <div className={css('la-thirds')} />
          <div className={css('la-cross')} />
        </div>
        <header className={css('la-top')}>
          {home ? (
            <Link className={css('la-brand')} to={home} title="About Scene.ai">
              {brand}
            </Link>
          ) : (
            <span className={css('la-brand')}>{brand}</span>
          )}
          <div className={css('la-readout la-mono')} aria-hidden="true">
            <Timecode />
            {(READOUT[scene] || []).map((t) => (
              <span key={t}>{t}</span>
            ))}
          </div>
          <span className={css('auth-spacer')} />
        </header>
        <div className={css('la-lower')}>
          <div>
            <h2 className={css('la-head')}>{heading}</h2>
            <p className={css('la-sub')}>{sub}</p>
            <ul className={css('auth-points la-mono')}>
              {points.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </div>
          <div className={css('la-slate auth-slate')}>
            <header className={css('la-mono')}>
              <span>{tag}</span>
              <span>Scene.ai</span>
            </header>
            <div className={css('auth-card')} role="region" aria-label="Sign-in form">
              {children}
            </div>
          </div>
        </div>
        <div className={css('la-meters')} aria-hidden="true">
          <i />
          <i />
          <i />
        </div>
      </SetMonitor>
      {below}
    </LandingRoot>
  );
}

/** The monitor of a sign-in page; with the landing's sections below it, it behaves as the landing's does. */
function SetMonitor({ withSections, children }: { withSections: boolean; children: ReactNode }) {
  const monitor = useRef<HTMLElement>(null);
  const off = useMonitorLife(monitor, withSections);
  return (
    <section ref={monitor} className={css('la-monitor' + (off ? ' off' : ''))}>
      {children}
      {withSections && <Cue />}
    </section>
  );
}

/** The timecode runs at 24 frames a second, from one hour in, and stops once the page is left. */
function Timecode() {
  const node = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const started = performance.now();
    let frame = 0;
    const tick = () => {
      if (node.current)
        node.current.textContent = frameTimecode(Math.floor((performance.now() - started) / (1000 / 24)) + 24 * 3600);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);
  return (
    <span ref={node} className={css('la-rec')} data-testid="timecode">
      01:00:00:00
    </span>
  );
}
