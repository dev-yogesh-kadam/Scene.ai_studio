// The rooftop at dusk, in 3D: a city in the haze, our roof, and her against the sun.

import * as THREE from 'three';
import { box, canvasTexture, glow, gradient, lerp, mix, person, seeded, sprite, type Set3D } from './kit';

export function rooftop(): Set3D {
  const rnd = seeded(7);
  const scene = new THREE.Scene();
  scene.background = gradient([
    [0, '#1b1640'],
    [0.45, '#6b2d5c'],
    [0.72, '#e2694a'],
    [0.86, '#ffb35c'],
    [1, '#ffb35c'],
  ]);
  scene.fog = new THREE.Fog(0xa84f66, 90, 640);
  scene.add(new THREE.HemisphereLight(0x8a5aa0, 0x150a18, 0.9));
  const sun = new THREE.DirectionalLight(0xffa868, 2.6);
  sun.position.set(60, 95, -700);
  scene.add(sun);
  const fill = new THREE.DirectionalLight(0x5a4aa0, 0.4);
  fill.position.set(-50, 30, 80);
  scene.add(fill);
  const halo = sprite(glow('rgba(255,243,214,1)', 'rgba(255,190,110,.55)'), [60, 95, -700], 620);
  scene.add(halo, sprite(glow('rgba(255,250,235,1)', 'rgba(255,240,210,.9)'), [60, 95, -698], 70));

  const lit = canvasTexture(64, 128, (g, w, h) => {
    g.fillStyle = '#000';
    g.fillRect(0, 0, w, h);
    for (let y = 0; y < 8; y += 1)
      for (let x = 0; x < 4; x += 1)
        if (rnd() > 0.62) {
          g.fillStyle = rnd() > 0.5 ? '#ffc477' : '#ffdca0';
          g.fillRect(x * 16 + 4, y * 16 + 5, 8, 7);
        }
  });
  lit.wrapS = lit.wrapT = THREE.RepeatWrapping;
  for (let i = 0; i < 420; i += 1) {
    const x = (rnd() - 0.5) * 1100,
      z = -95 - rnd() * 560;
    if (Math.abs(x) < 40 && z > -130) continue;
    const w = 10 + rnd() * 22,
      d = 10 + rnd() * 22,
      h = 8 + rnd() * rnd() * 42 + Math.max(0, (-z - 200) / 7) * (0.4 + rnd());
    const windows = lit.clone();
    windows.repeat.set(Math.max(1, Math.round(w / 8)), Math.max(1, Math.round(h / 16)));
    const m = new THREE.MeshStandardMaterial({
      color: new THREE.Color().setHSL(0.86, 0.25, 0.07 + rnd() * 0.05),
      roughness: 0.85,
      emissive: 0xffffff,
      emissiveIntensity: 1.2,
      emissiveMap: windows,
    });
    scene.add(box(m, [w, h, d], [x, h / 2 - 30, z]));
    if (rnd() > 0.85) {
      const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.3, 12 + rnd() * 18, 6), m);
      mast.position.set(x, h - 22, z);
      scene.add(mast);
    }
  }
  // our roof: the parapet, a water tank on legs and the air units
  const dark = new THREE.MeshLambertMaterial({ color: 0x0d0811 });
  scene.add(
    box(dark, [60, 30, 70], [0, -15, -15]),
    box(dark, [60, 0.9, 0.4], [0, 0.45, -50]),
    box(dark, [0.4, 0.9, 70], [-30, 0.45, -15]),
    box(dark, [0.4, 0.9, 70], [30, 0.45, -15]),
  );
  const tank = new THREE.Mesh(new THREE.CylinderGeometry(2.4, 2.4, 4, 24), dark);
  tank.position.set(-16, 6.5, -47);
  const cap = new THREE.Mesh(new THREE.ConeGeometry(2.7, 1.4, 24), dark);
  cap.position.set(-16, 9.2, -47);
  scene.add(tank, cap);
  for (const [x, z] of [
    [-17.6, -48.6],
    [-14.4, -48.6],
    [-17.6, -45.4],
    [-14.4, -45.4],
  ]) {
    const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 4.5, 6), dark);
    leg.position.set(x, 2.25, z);
    scene.add(leg);
  }
  scene.add(
    box(dark, [2.4, 1.4, 1.8], [8, 0.7, -40]),
    box(dark, [2.4, 1.4, 1.8], [12, 0.7, -40]),
    box(dark, [2.4, 1.4, 1.8], [-4, 0.7, -44]),
  );
  const her = person(0x0d0811);
  her.position.set(0.4, 0, -46);
  her.rotation.y = 0.3;
  scene.add(her);
  const rim = new THREE.PointLight(0xffb070, 9, 0, 2);
  rim.position.set(0.9, 1.8, -47.4);
  scene.add(rim);

  return {
    scene,
    tick({ t }) {
      her.rotation.z = Math.sin(t * 0.8) * 0.015;
      halo.scale.setScalar(620 * (1 + Math.sin(t * 0.6) * 0.04));
    },
    cam(i, p) {
      if (i === 0) return { pos: mix([-1, 1.4, -34], [-1, 1.5, -35.4], p), look: [3, 4, -200], fov: 30 };
      if (i === 1)
        return { pos: mix([2.2, 1.75, -42.4], [1.6, 1.72, -43.5], p), look: [0.3, 1.5, -46.5], fov: lerp(28, 24, p) };
      return { pos: mix([0, 1.7, -44], [0.6, 2.2, -49], p), look: [40, 60, -650], fov: lerp(40, 16, p) };
    },
  };
}
