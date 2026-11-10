// Motion that behaves like a thing in the hand, after Apple's "Designing Fluid Interfaces" (the classic spring.js).
// A spring has no fixed length of time: it starts from where the thing is now, at the speed it is moving, so it can be
// caught and sent somewhere else at any moment without a jump. A drag hands over the pointer's speed when it ends.
// Two numbers describe a spring: damping (1 settles without overshoot, 0.8 overshoots a little and is kept for flicks)
// and response (roughly the seconds it takes to get there; lower is snappier).

import { reducedMotion } from '../hooks/useAppearance';

export type SpringTo = { damping?: number; response?: number; velocity?: number; done?: () => void };

/** A value moved by a spring. apply(x) puts it on screen; precision is how close counts as there (px by default). */
export class Spring {
  x: number;
  v = 0;
  private raf = 0;

  constructor(
    value: number,
    private apply: (x: number) => void,
    private precision = 0.25,
  ) {
    this.x = value;
    apply(value);
  }

  get moving() {
    return this.raf !== 0;
  }

  /** Puts it at x at once, as a drag does, and forgets the speed (the pointer's own speed is measured by tracker()). */
  set(x: number) {
    this.stop();
    this.x = x;
    this.v = 0;
    this.apply(x);
  }

  stop() {
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = 0;
  }

  /** Moves to target from where it is now. velocity (units a second) is handed over from a drag; left out, the spring
   *  keeps the speed it already has, so turning it around mid-flight does not hit a wall. */
  to(target: number, { damping = 1, response = 0.4, velocity, done }: SpringTo = {}) {
    this.stop();
    if (velocity !== undefined) this.v = velocity;
    if (reducedMotion()) {
      // calm motion: there at once
      this.x = target;
      this.v = 0;
      this.apply(target);
      done?.();
      return this;
    }
    const stiffness = ((2 * Math.PI) / response) ** 2;
    const friction = (4 * Math.PI * damping) / response;
    let last = performance.now();
    const frame = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000); // a tab that was hidden does not jump
      last = now;
      const steps = Math.max(1, Math.ceil(dt / 0.004));
      const h = dt / steps;
      for (let i = 0; i < steps; i += 1) {
        this.v += (-stiffness * (this.x - target) - friction * this.v) * h;
        this.x += this.v * h;
      }
      if (Math.abs(this.v) < this.precision * 16 && Math.abs(this.x - target) < this.precision) {
        this.x = target;
        this.v = 0;
        this.raf = 0;
        this.apply(target);
        done?.();
        return;
      }
      this.apply(this.x);
      this.raf = requestAnimationFrame(frame);
    };
    this.raf = requestAnimationFrame(frame);
    return this;
  }
}

/** The pointer's speed when it lets go, from its last 100 ms of moves (px a second). A pointer that stopped before
 *  letting go has no speed. */
export function tracker() {
  let points: { x: number; y: number; t: number }[] = [];
  return {
    add(x: number, y = 0) {
      points.push({ x, y, t: performance.now() });
      if (points.length > 20) points.shift();
    },
    velocity() {
      const now = performance.now();
      const recent = points.filter((p) => now - p.t < 100);
      if (recent.length < 2) return { x: 0, y: 0 };
      const a = recent[0];
      const b = recent[recent.length - 1];
      const dt = Math.max(0.001, (b.t - a.t) / 1000);
      return { x: (b.x - a.x) / dt, y: (b.y - a.y) / dt };
    },
    reset() {
      points = [];
    },
  };
}

/** How far a flick at this speed would carry on, as scrolling slows down (Apple's own function). */
export const project = (velocity: number, rate = 0.998) => ((velocity / 1000) * rate) / (1 - rate);

/** Past an edge a thing follows less and less, the way a real one slows before it stops. */
export const rubberband = (over: number, size: number, c = 0.55) => (over * size * c) / (size + c * Math.abs(over));
