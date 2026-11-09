// The drawn set on the landing page's monitor: a scene of landing-scenes.js with each of its planes on a layer of its
// own, so a camera can move through them. A zoom grows the near planes more than the sky, a sideways move slides
// them past faster, and the lens keeps one depth sharp and softens the rest. A shot is a move from one framing to
// another over its length; the browser plays it as a transition, so nothing runs per frame. The mouse leans the
// planes by depth on top of that (app.css reads --px and --py from the monitor).

import * as scenes from './landing-scenes.js';

const EASE = 'cubic-bezier(.37, 0, .63, 1)';   // a dolly starts and stops gently

export function drawnSet() {
  const node = document.createElement('div');
  node.className = 'la-stage';
  node.setAttribute('aria-hidden', 'true');
  let layers = [], last = null;

  // Where a framing puts each plane: the drawing is fitted to the box as a slice (like the <svg>s inside), then each
  // plane is scaled about the framing's point by its share of the zoom and slid by its share of the sideways move.
  function place(c, ms) {
    const w = node.clientWidth || window.innerWidth, h = node.clientHeight || window.innerHeight;
    const fit = Math.max(w / 1600, h / 900), ox = (w - 1600 * fit) / 2, oy = (h - 900 * fit) / 2;
    const fx = ox + c.fx * fit, fy = oy + c.fy * fit;
    for (const { n, z } of layers) {
      const s = Math.pow(c.k, 0.3 + 0.7 * z);
      const tx = fx * (1 - s) - (c.px || 0) * 90 * z * fit, ty = fy * (1 - s);
      const blur = Math.abs(z - c.f) * c.b * (w / 1920);
      n.style.transition = ms ? `transform ${ms}ms ${EASE}, filter ${ms}ms ${EASE}` : 'none';
      n.style.transform = `translate(${tx.toFixed(1)}px, ${ty.toFixed(1)}px) scale(${s.toFixed(4)})`;
      n.style.filter = blur > 0.3 ? `blur(${blur.toFixed(1)}px)` : 'none';
    }
  }

  return {
    node,
    // Build the set of a scene, framed wide and still.
    show(name) {
      const { defs, planes } = scenes.planes(name);
      node.innerHTML = `<svg class="la-defs" width="0" height="0" aria-hidden="true"><defs>${defs}</defs></svg>` +
        planes.map(({ z, body }) => `<div class="la-plane" style="--z:${z}"><div class="la-lean"><svg viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">${body}</svg></div></div>`).join('');
      layers = [...node.querySelectorAll('.la-plane')].map((n) => ({ n, z: +n.style.getPropertyValue('--z') }));
      node.classList.remove('shake');
      last = scenes.info(name).camera[0].from;
      place(last, 0);
    },
    // Play a shot: cut to its first framing, then move to its last over the shot. ms 0 cuts straight to the last.
    shot(camera, ms) {
      node.classList.toggle('shake', !!camera.shake && ms > 0);
      place(camera.from, 0);
      if (!ms) { place(last = camera.to, 0); return; }
      void node.offsetWidth;   // the first framing is laid out before the move starts from it
      place(last = camera.to, ms);
    },
    // The box changed size: frame the same again, without a move.
    resize() { if (last) place(last, 0); },
  };
}
