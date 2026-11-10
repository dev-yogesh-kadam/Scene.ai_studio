// The canvas's camera: where the board is and how near. It moves on springs: a flicked board carries on and settles,
// and Fit or a result picked in the conversation glides there. Touching the board, the wheel or a zoom catches it where
// it is. It moves the world layer itself (a transform on one element, every frame of a move) and tells whoever listens
// (the zoom on the bar, the bar over the selection, the minimap), so React draws nothing while it moves.

import { Spring, project as carry, rubberband } from '../../../common/motion/spring';
import { FRAME, LABEL, MAX_ZOOM, MIN_ZOOM, SLATE, bounds, clamp } from './geometry';

export type Cam = { x: number; y: number; k: number };
export type Box = { x: number; y: number; h: number };
type Edges = { minX: number; maxX: number; w: number; minY: number; maxY: number; h: number };

export class Camera {
  cam: Cam = { x: 96, y: 96, k: 1 };
  private stage: HTMLElement | null = null;
  private world: HTMLElement | null = null;
  private moves: Spring[] = [];
  private listeners = new Set<() => void>();
  /** What is on the canvas now, for Fit, the limits and the way back. */
  boxes: Box[] = [];
  /** How much of the right side the open panel covers. */
  covered = 0;

  attach(stage: HTMLElement | null, world: HTMLElement | null) {
    this.stage = stage;
    this.world = world;
    if (stage && world) this.apply();
  }

  /** What is on the canvas, and how much of it the panel covers: Fit, the limits and the way back follow them. */
  update(boxes: Box[], covered: number) {
    this.boxes = boxes;
    this.covered = covered;
    this.apply();
  }

  subscribe = (fn: () => void) => {
    this.listeners.add(fn);
    return () => void this.listeners.delete(fn);
  };

  /** The zoom in percent, for the bar. */
  zoom = () => Math.round(this.cam.k * 100);

  rect() {
    return this.stage?.getBoundingClientRect() ?? new DOMRect(0, 0, 0, 0);
  }

  apply() {
    const { x, y, k } = this.cam;
    if (this.world) {
      this.world.style.transform = `translate(${x}px, ${y}px) scale(${k})`;
      this.world.style.setProperty('--inv', String(1 / k));
    }
    if (this.stage) {
      this.stage.style.setProperty('--grid', 96 * k + 'px');
      this.stage.style.setProperty('--grid-x', x + 'px');
      this.stage.style.setProperty('--grid-y', y + 'px');
      this.stage.toggleAttribute('data-far', k < 0.5); // far away: just the pictures, no slates or grid
    }
    for (const fn of [...this.listeners]) fn();
  }

  stop() {
    this.moves.forEach((spring) => spring.stop());
    this.moves = [];
  }

  glideTo(to: Cam) {
    this.stop();
    const from = { ...this.cam };
    this.moves = [
      new Spring(
        0,
        (p) => {
          this.cam = {
            x: from.x + (to.x - from.x) * p,
            y: from.y + (to.y - from.y) * p,
            k: from.k + (to.k - from.k) * p,
          };
          this.apply();
        },
        0.001,
      ).to(1, { response: 0.5 }),
    ];
  }

  /** How far the board can be pushed: some of the work always stays in sight, so it is never lost off an edge. */
  limits(): Edges | null {
    if (!this.boxes.length) return null;
    const all = bounds(this.boxes);
    const rect = this.rect();
    const keep = 160;
    const k = this.cam.k;
    return {
      minX: keep - all.right * k,
      maxX: rect.width - keep - (all.x - LABEL) * k,
      w: rect.width,
      minY: keep - all.bottom * k,
      maxY: rect.height - keep - all.y * k,
      h: rect.height,
    };
  }

  /** Past a limit the board follows the pointer less and less. */
  static soft(raw: number, low: number, high: number, size: number) {
    return raw < low ? low - rubberband(low - raw, size) : raw > high ? high + rubberband(raw - high, size) : raw;
  }

  /** A drag let go: the board carries on at the pointer's speed and settles inside its limits. */
  throwWith(velocity: { x: number; y: number }) {
    this.stop();
    const edge = this.limits();
    if (!edge) return;
    const axis = (key: 'x' | 'y', speed: number, low: number, high: number) => {
      const out = this.cam[key] < low || this.cam[key] > high;
      return new Spring(this.cam[key], (value) => {
        this.cam = { ...this.cam, [key]: value };
        this.apply();
      }).to(clamp(this.cam[key] + carry(speed), low, high), { response: out ? 0.45 : 0.8, velocity: speed });
    };
    this.moves = [axis('x', velocity.x, edge.minX, edge.maxX), axis('y', velocity.y, edge.minY, edge.maxY)];
  }

  moveTo(x: number, y: number) {
    this.cam = { ...this.cam, x, y };
    this.apply();
  }

  zoomAt(clientX: number, clientY: number, k: number) {
    this.stop();
    const rect = this.rect();
    const px = clientX - rect.left;
    const py = clientY - rect.top;
    const wx = (px - this.cam.x) / this.cam.k;
    const wy = (py - this.cam.y) / this.cam.k;
    const next = clamp(k, MIN_ZOOM, MAX_ZOOM);
    this.cam = { k: next, x: px - wx * next, y: py - wy * next };
    this.apply();
  }

  zoomTo(k: number) {
    const rect = this.rect();
    this.zoomAt(rect.left + rect.width / 2, rect.top + rect.height / 2, k);
  }

  /** animate: glide there (Fit, the 1 key); otherwise jump, as when the page opens or the panel is resized. */
  fit(animate = false) {
    if (!this.boxes.length) {
      this.stop();
      this.cam = { x: 96, y: 96, k: 1 };
      this.apply();
      return;
    }
    const all = bounds(this.boxes);
    all.x -= LABEL; // the names of the shots are part of the picture
    const rect = this.rect();
    const room = { w: rect.width - 160 - this.covered, h: rect.height - 160 };
    const k = clamp(Math.min(room.w / (all.right - all.x), room.h / (all.bottom - all.y)), MIN_ZOOM, 1);
    const to = {
      k,
      x: (rect.width - this.covered - (all.right - all.x) * k) / 2 - all.x * k,
      y: 80 + (room.h - (all.bottom - all.y) * k) / 2 - all.y * k,
    };
    if (animate) return this.glideTo(to);
    this.stop();
    this.cam = to;
    this.apply();
  }

  /** Glide to one frame: to the middle of the part of the canvas the panel leaves free, at a size it can be seen at. */
  focus(box: Box) {
    const rect = this.rect();
    const room = { w: Math.max(200, rect.width - this.covered), h: rect.height };
    const k = clamp(Math.min((room.w * 0.55) / FRAME, (room.h * 0.62) / (box.h + SLATE)), 0.35, 1.6);
    this.glideTo({ k, x: room.w / 2 - (box.x + FRAME / 2) * k, y: room.h / 2 - (box.y + (box.h + SLATE) / 2) * k });
  }

  /** Whether any of the work is in sight (not under the bars or the panel). */
  inSight() {
    const rect = this.rect();
    const { x, y, k } = this.cam;
    return this.boxes.some(
      (b) =>
        x + b.x * k < rect.width - this.covered - 40 &&
        x + (b.x + FRAME) * k > 40 &&
        y + b.y * k < rect.height - 40 &&
        y + (b.y + b.h + SLATE) * k > 70,
    );
  }

  /** The part of the world in view, in canvas units, with a margin of `margin` screens around it. */
  seen(margin = 0) {
    const rect = this.rect();
    const { x, y, k } = this.cam;
    const w = rect.width / k;
    const h = rect.height / k;
    return {
      x: -x / k - w * margin,
      y: -y / k - h * margin,
      right: -x / k + w * (1 + margin),
      bottom: -y / k + h * (1 + margin),
    };
  }
}

/** Follows the pointer until it is let go (on the window, so a fast drag that leaves the element still counts). */
export function track(onMove: (e: PointerEvent) => void, onEnd: () => void) {
  const end = () => {
    window.removeEventListener('pointermove', onMove);
    window.removeEventListener('pointerup', end);
    onEnd();
  };
  window.addEventListener('pointermove', onMove);
  window.addEventListener('pointerup', end);
}
