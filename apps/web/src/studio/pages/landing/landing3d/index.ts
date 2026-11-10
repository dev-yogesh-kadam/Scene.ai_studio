// The landing page's sets built in 3D: the four scenes of landingScenes as small worlds of boxes, cylinders and light
// (Three.js), with a real camera for every shot of their plans. The monitor loads this only where it can run (WebGL, the
// full motion setting, a big enough screen) and keeps the drawn set otherwise. The page calls frame() from its own
// clock, so nothing renders while the monitor is out of sight.

import * as THREE from 'three';
import { deep } from './deep';
import { desert } from './desert';
import { ease, type Set3D } from './kit';
import { neon } from './neon';
import { rooftop } from './rooftop';

const SETS: Record<string, () => Set3D> = { rooftop, neon, desert, deep };

function dispose(scene: THREE.Scene) {
  scene.traverse((o) => {
    const { geometry, material } = o as THREE.Mesh;
    geometry?.dispose();
    for (const m of ([] as THREE.Material[]).concat(material || [])) {
      for (const v of Object.values(m) as (THREE.Texture | null)[]) if (v?.isTexture) v.dispose();
      m.dispose();
    }
  });
  const background = scene.background as THREE.Texture | null;
  if (background?.isTexture) background.dispose();
}

export type Three = ReturnType<typeof create>;

export function create(canvas: HTMLCanvasElement) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.1;
  const camera = new THREE.PerspectiveCamera(30, 16 / 9, 0.1, 3000);
  let set: Set3D | null = null,
    shot = 0,
    shotAt = 0,
    shotMs = 0,
    sceneAt = 0;
  const lean = { x: 0, y: 0, tx: 0, ty: 0 };

  return {
    show(name: string) {
      if (set) dispose(set.scene);
      set = SETS[name]();
      shot = 0;
      shotAt = sceneAt = performance.now();
      shotMs = 0;
    },
    shot(i: number, ms: number, at = performance.now()) {
      shot = i;
      shotAt = at;
      shotMs = ms;
    },
    pointer(x: number, y: number) {
      lean.tx = x;
      lean.ty = y;
    },
    size(w: number, h: number) {
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    },
    frame(now: number) {
      if (!set) return;
      const st = { t: now / 1000, shot: (now - shotAt) / 1000, scene: (now - sceneAt) / 1000 };
      const p = shotMs ? ease(Math.min(1, (now - shotAt) / shotMs)) : 1;
      set.tick(st, shot);
      const c = set.cam(shot, p, st);
      lean.x += (lean.tx - lean.x) * 0.05;
      lean.y += (lean.ty - lean.y) * 0.05; // the mouse leans the camera, softly
      camera.position.set(c.pos[0] + lean.x * 0.35, c.pos[1] - lean.y * 0.18, c.pos[2]);
      camera.lookAt(c.look[0], c.look[1], c.look[2]);
      if (camera.fov !== c.fov) {
        camera.fov = c.fov;
        camera.updateProjectionMatrix();
      }
      renderer.render(set.scene, camera);
    },
    dispose() {
      if (set) dispose(set.scene);
      set = null;
      renderer.dispose();
    },
  };
}
