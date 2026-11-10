// The drawn set on the landing page's monitor: a scene of landingScenes with each of its planes on a layer of its own,
// so a camera can move through them. A zoom grows the near planes more than the sky, a sideways move slides them past
// faster, and the lens keeps one depth sharp and softens the rest. A shot is a move from one framing to another over
// its length; the browser plays it as a transition, so nothing runs per frame. The mouse leans the planes by depth on
// top of that (the CSS reads --px and --py from the monitor).

import { useImperativeHandle, useRef, useState, type CSSProperties, type Ref } from 'react';
import { flushSync } from 'react-dom';
import { SvgDrawing } from '../../../common/components/SvgDrawing';
import * as scenes from '../../../common/landing/landingScenes';
import type { Framing, ShotCamera } from '../../../common/landing/landingScenes';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/landing/Landing5.module.css';
import css1 from '../../../common/landing/Landing6.module.css';
import css2 from '../../../common/landing/landingScenes.module.css';
const css = classesOf(css0, css1, css2);

const EASE = 'cubic-bezier(.37, 0, .63, 1)'; // a dolly starts and stops gently

export type DrawnHandle = {
  show: (name: string) => void;
  shot: (camera: ShotCamera, ms: number) => void;
  resize: () => void;
};

export function DrawnSet({ ref }: { ref: Ref<DrawnHandle> }) {
  const [drawn, setDrawn] = useState<{ name: string; defs: string; planes: { z: number; body: string }[] } | null>(
    null,
  );
  const [shake, setShake] = useState(false);
  const stage = useRef<HTMLDivElement>(null);
  const layers = useRef<(HTMLDivElement | null)[]>([]);
  const last = useRef<Framing | null>(null);

  useImperativeHandle(ref, () => {
    // Where a framing puts each plane: the drawing is fitted to the box as a slice (like the <svg>s inside), then each
    // plane is scaled about the framing's point by its share of the zoom and slid by its share of the sideways move.
    const place = (c: Framing, ms: number) => {
      const w = stage.current?.clientWidth || window.innerWidth,
        h = stage.current?.clientHeight || window.innerHeight;
      const fit = Math.max(w / 1600, h / 900),
        ox = (w - 1600 * fit) / 2,
        oy = (h - 900 * fit) / 2;
      const fx = ox + c.fx * fit,
        fy = oy + c.fy * fit;
      for (const n of layers.current) {
        if (!n) continue;
        const z = Number(n.style.getPropertyValue('--z'));
        const s = Math.pow(c.k, 0.3 + 0.7 * z);
        const tx = fx * (1 - s) - (c.px || 0) * 90 * z * fit,
          ty = fy * (1 - s);
        const blur = Math.abs(z - c.f) * c.b * (w / 1920);
        n.style.transition = ms ? `transform ${ms}ms ${EASE}, filter ${ms}ms ${EASE}` : 'none';
        n.style.transform = `translate(${tx.toFixed(1)}px, ${ty.toFixed(1)}px) scale(${s.toFixed(4)})`;
        n.style.filter = blur > 0.3 ? `blur(${blur.toFixed(1)}px)` : 'none';
      }
    };
    return {
      // Build the set of a scene, framed wide and still.
      show(name) {
        flushSync(() => {
          setDrawn({ name, ...scenes.planes(name) });
          setShake(false);
        });
        last.current = scenes.info(name).camera[0].from;
        place(last.current, 0);
      },
      // Play a shot: cut to its first framing, then move to its last over the shot. ms 0 cuts straight to the last.
      shot(camera, ms) {
        flushSync(() => setShake(!!camera.shake && ms > 0));
        place(camera.from, 0);
        last.current = camera.to;
        if (!ms) {
          place(camera.to, 0);
          return;
        }
        void stage.current?.offsetWidth; // the first framing is laid out before the move starts from it
        place(camera.to, ms);
      },
      // The box changed size: frame the same again, without a move.
      resize() {
        if (last.current) place(last.current, 0);
      },
    };
  }, []);

  return (
    <div ref={stage} className={css('la-stage' + (shake ? ' shake' : ''))} aria-hidden="true">
      {drawn && (
        <>
          <SvgDrawing
            className={css('la-defs')}
            svg={`<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0" aria-hidden="true"><defs>${drawn.defs}</defs></svg>`}
          />
          {drawn.planes.map(({ z, body }, i) => (
            <div
              key={drawn.name + i}
              className={css('la-plane')}
              data-testid="set-plane"
              style={{ '--z': String(z) } as CSSProperties}
              ref={(n) => {
                layers.current[i] = n;
              }}
            >
              <SvgDrawing
                className={css('la-lean')}
                svg={`<svg viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">${body}</svg>`}
              />
            </div>
          ))}
        </>
      )}
    </div>
  );
}
