// The neon alley, in 3D: wet ground, signs that light the walls, rain, and the runner.

import * as THREE from 'three';
import { box, glow, mix, person, seeded, sprite, stride, type Set3D } from './kit';

export function neon(): Set3D {
  const rnd = seeded(11);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x05070f);
  scene.fog = new THREE.FogExp2(0x0b1730, 0.035);
  scene.add(new THREE.HemisphereLight(0x2a3a70, 0x02030a, 1.1));
  const wall = new THREE.MeshStandardMaterial({ color: 0x1a2034, roughness: 0.85 });
  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(9, 90),
    new THREE.MeshStandardMaterial({ color: 0x0a1226, roughness: 0.08, metalness: 0.85 }),
  );
  floor.rotation.x = -Math.PI / 2;
  floor.position.z = -40;
  scene.add(floor);
  scene.add(
    box(wall, [1, 16, 90], [-5, 8, -40]),
    box(wall, [1, 16, 90], [5, 8, -40]),
    box(new THREE.MeshStandardMaterial({ color: 0x101c38, roughness: 0.9 }), [10, 16, 1], [0, 8, -70]),
  );
  for (let i = 0; i < 26; i += 1) {
    // doors, pipes and boxes on the walls
    const side = i % 2 ? 1 : -1;
    scene.add(box(wall, [0.5, 0.6 + rnd() * 1.6, 0.8 + rnd() * 2], [side * 4.3, 1 + rnd() * 9, -4 - rnd() * 60]));
  }
  const pipe = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 90, 8), wall);
  pipe.rotation.x = Math.PI / 2;
  pipe.position.set(-4.3, 7.5, -40);
  scene.add(pipe);
  const signs: {
    face: THREE.MeshBasicMaterial;
    light: THREE.PointLight;
    halo: THREE.Sprite;
    colour: number;
    base: number;
  }[] = [];
  for (const [colour, x, y, z, w, h, d] of [
    [0xff2e88, -4.45, 4.6, -9, 0.2, 1.1, 3.2],
    [0x22e3ff, 4.45, 4.2, -16, 0.2, 3.6, 0.9],
    [0xffb02e, 0, 6.2, -69.3, 3.4, 0.6, 0.2],
    [0xff2e88, 4.45, 7, -34, 0.2, 0.8, 2.4],
    [0x22e3ff, -4.45, 3, -44, 0.2, 2.2, 0.8],
  ]) {
    const face = new THREE.MeshBasicMaterial({ color: colour });
    scene.add(box(face, [w, h, d], [x, y, z]));
    const light = new THREE.PointLight(colour, 70, 0, 2);
    light.position.set(x * 0.8, y, z);
    scene.add(light);
    const c = new THREE.Color(colour),
      rgba = (a: number) => `rgba(${Math.round(c.r * 255)},${Math.round(c.g * 255)},${Math.round(c.b * 255)},${a})`;
    const halo = sprite(glow(rgba(0.9), rgba(0.35)), [x * 0.92, y, z], Math.max(h, d) * 3.4, { opacity: 0.8 });
    scene.add(halo);
    signs.push({ face, light, halo, colour, base: light.intensity });
  }
  // rain: streaks in a box twice the height of the alley, slid down and wrapped, so it never runs out
  const streaks: number[] = [];
  for (let i = 0; i < 5000; i += 1) {
    const x = (rnd() - 0.5) * 9,
      y = rnd() * 28,
      z = 4 - rnd() * 70;
    streaks.push(x, y, z, x - 0.04, y - 0.5, z);
  }
  const rainGeo = new THREE.BufferGeometry();
  rainGeo.setAttribute('position', new THREE.Float32BufferAttribute(streaks, 3));
  const rain = new THREE.LineSegments(
    rainGeo,
    new THREE.LineBasicMaterial({ color: 0x9fb6ff, transparent: true, opacity: 0.32 }),
  );
  scene.add(rain);
  const runner = person(0x05060c);
  scene.add(runner);
  const breath = sprite(glow('rgba(220,235,255,.55)', 'rgba(200,220,255,.18)'), [0, 0, 0], 0.6, { add: false });
  const backlight = new THREE.PointLight(0x22e3ff, 0, 0, 2); // the sign behind the runner, lighting the edges in the close-up
  scene.add(breath, backlight);

  return {
    scene,
    tick({ t, shot }, i) {
      rain.position.y = -((t * 18) % 14);
      const flicker = Math.sin(t * 23) > 0.93 || (t % 5 > 3.1 && t % 5 < 3.25); // the first pink sign stutters
      signs[0].face.color.setHex(flicker ? 0x40122a : signs[0].colour);
      signs[0].light.intensity = flicker ? 2 : signs[0].base;
      signs[0].halo.material.opacity = flicker ? 0.1 : 0.8;
      if (i < 2) {
        // running away down the alley; a new shot starts the run again (the cut hides it)
        runner.position.set(0.9, Math.abs(Math.sin(t * 9)) * 0.06, -6 - shot * 1.7);
        runner.rotation.set(0, -0.25, 0.08);
        stride(runner, t, 9);
        breath.visible = false;
        backlight.intensity = 0;
      } else {
        // stopped, turned to the camera, breathing out into the cold
        runner.position.set(0.9, 0, -14);
        runner.rotation.set(0, -0.3, 0);
        backlight.position.set(1.6, 1.9, -15.4);
        backlight.intensity = 14;
        stride(runner, t, 1.6, 0.03);
        const out = (t * 0.55) % 1;
        breath.visible = true;
        breath.position.set(0.8 - out * 0.25, 1.62 + out * 0.15, -13.75 + out * 0.5);
        breath.scale.setScalar(0.25 + out * 0.8);
        breath.material.opacity = Math.sin(out * Math.PI) * 0.7;
      }
    },
    cam(i, p) {
      const r = runner.position;
      if (i === 0) return { pos: mix([-1.6, 0.45, -2], [-1.4, 0.5, -3.2], p), look: [1.2, 3.2, -30], fov: 46 };
      if (i === 1) return { pos: [r.x - 2.2, 1.3, r.z + 4.6], look: [r.x, 1.2, r.z - 3], fov: 40 };
      return { pos: mix([-0.3, 1.62, -10.4], [-0.05, 1.6, -11.1], p), look: [0.9, 1.4, -14], fov: 34 };
    },
  };
}
