// What the landing page's 3D sets are built from: textures drawn on a canvas, glows, boxes and people.

import * as THREE from 'three';

/** Seconds of the page, into the shot and on this set. */
export type Moment = { t: number; shot: number; scene: number };
export type Cam = { pos: number[]; look: number[]; fov: number };
/** A set: its scene, what moves in it, and where shot i's camera is at p (0 to 1 through the shot). */
export type Set3D = {
  scene: THREE.Scene;
  tick: (moment: Moment, shot: number) => void;
  cam: (shot: number, p: number, moment: Moment) => Cam;
};

export const lerp = (a: number, b: number, p: number) => a + (b - a) * p;
export const mix = (a: number[], b: number[], p: number) => a.map((v, i) => lerp(v, b[i], p));
export const ease = (p: number) => (p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2);

export function seeded(seed: number) {
  let s = seed;
  return () => (s = (s * 9301 + 49297) % 233280) / 233280;
}

export function canvasTexture(w: number, h: number, draw: (g: CanvasRenderingContext2D, w: number, h: number) => void) {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  draw(c.getContext('2d') as CanvasRenderingContext2D, w, h);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

export const gradient = (stops: [number, string][]) =>
  canvasTexture(4, 512, (g, w, h) => {
    const l = g.createLinearGradient(0, 0, 0, h);
    stops.forEach(([at, colour]) => l.addColorStop(at, colour));
    g.fillStyle = l;
    g.fillRect(0, 0, w, h);
  });

export const glow = (inner: string, outer: string) =>
  canvasTexture(256, 256, (g) => {
    const r = g.createRadialGradient(128, 128, 0, 128, 128, 128);
    r.addColorStop(0, inner);
    r.addColorStop(0.25, outer);
    r.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = r;
    g.fillRect(0, 0, 256, 256);
  });

export function sprite(
  map: THREE.Texture,
  [x, y, z]: number[],
  size: number,
  { opacity = 1, add = true }: { opacity?: number; add?: boolean } = {},
) {
  const s = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map,
      transparent: true,
      opacity,
      depthWrite: false,
      fog: false,
      blending: add ? THREE.AdditiveBlending : THREE.NormalBlending,
    }),
  );
  s.position.set(x, y, z);
  s.scale.set(size, size, 1);
  return s;
}

export function box(material: THREE.Material, [w, h, d]: number[], [x, y, z]: number[]) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material);
  m.position.set(x, y, z);
  return m;
}

// A person of rounded solids, 1.75 tall, with hips and shoulders that swing.
type Limbs = { legs: THREE.Group[]; arms: THREE.Group[] };

export function person(colour: number) {
  const m = new THREE.MeshStandardMaterial({ color: colour, roughness: 0.8 });
  const g = new THREE.Group();
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.115, 24, 18), m);
  head.position.y = 1.64;
  head.scale.set(1, 1.12, 1.02);
  g.add(head);
  const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.16, 0.42, 6, 16), m);
  body.position.y = 1.2;
  body.scale.z = 0.75;
  g.add(body);
  const limb = (length: number, r: number, x: number, y: number, tilt = 0) => {
    const pivot = new THREE.Group();
    pivot.position.set(x, y, 0);
    pivot.rotation.z = tilt;
    const part = new THREE.Mesh(new THREE.CapsuleGeometry(r, length, 4, 10), m);
    part.position.y = -length / 2 - r;
    pivot.add(part);
    g.add(pivot);
    return pivot;
  };
  g.userData.legs = [limb(0.72, 0.068, -0.09, 0.9), limb(0.72, 0.068, 0.09, 0.9)];
  g.userData.arms = [limb(0.5, 0.048, -0.21, 1.48, -0.08), limb(0.5, 0.048, 0.21, 1.48, 0.08)];
  return g;
}

export function stride(who: THREE.Group, t: number, speed: number, size = 0.7) {
  const limbs = who.userData as Limbs;
  const [l, r] = limbs.legs,
    [a, b] = limbs.arms,
    s = Math.sin(t * speed);
  l.rotation.x = s * size;
  r.rotation.x = -s * size;
  a.rotation.x = -s * size * 0.8;
  b.rotation.x = s * size * 0.8;
}
