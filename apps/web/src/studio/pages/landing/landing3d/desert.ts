// The desert chase, in 3D: dunes, the jeep and its dust.

import * as THREE from 'three';
import { box, glow, gradient, lerp, mix, sprite, type Cam, type Set3D } from './kit';

export function desert(): Set3D {
  const scene = new THREE.Scene();
  scene.background = gradient([
    [0, '#5aa9d6'],
    [0.55, '#bfe0ea'],
    [0.7, '#f7e3c0'],
    [1, '#f7e3c0'],
  ]);
  scene.fog = new THREE.Fog(0xead2ae, 80, 480);
  scene.add(new THREE.HemisphereLight(0xbfe0ff, 0x8a5a30, 0.9));
  const sun = new THREE.DirectionalLight(0xfff2dd, 3.4);
  sun.position.set(220, 60, -260);
  scene.add(sun);
  scene.add(
    sprite(glow('rgba(255,250,240,1)', 'rgba(255,240,215,.5)'), [180, 120, -500], 160),
    sprite(glow('rgba(255,255,250,1)', 'rgba(255,252,240,.95)'), [180, 120, -499], 30),
  );
  // dunes: a wide sheet lifted by a few waves, flattened along the track the jeep drives (z = 0). The near side, where
  // the cameras stand (z > 0), stays low, so no dune ever comes between a camera and the jeep; the far side is the backdrop.
  const height = (x: number, z: number) => {
    const away = Math.min(1, Math.abs(z) / 14);
    return (
      (6 * Math.sin(x * 0.02) + 4 * Math.sin(z * 0.03 + 1) + 2.5 * Math.sin((x + z) * 0.05) + 3) *
      away *
      away *
      (z > 0 ? 0.25 : 1)
    );
  };
  const above = (c: Cam) => ({ ...c, pos: [c.pos[0], Math.max(c.pos[1], height(c.pos[0], c.pos[2]) + 1.4), c.pos[2]] }); // never in the sand
  const sand = new THREE.PlaneGeometry(900, 900, 160, 160);
  sand.rotateX(-Math.PI / 2);
  const at = sand.attributes.position;
  for (let i = 0; i < at.count; i += 1) at.setY(i, height(at.getX(i), at.getZ(i)));
  sand.computeVertexNormals();
  scene.add(new THREE.Mesh(sand, new THREE.MeshStandardMaterial({ color: 0xc98a4a, roughness: 1 })));
  // the jeep
  const paint = new THREE.MeshStandardMaterial({ color: 0x6a4a2a, roughness: 0.7 });
  const black = new THREE.MeshStandardMaterial({ color: 0x1a120c, roughness: 0.9 });
  const jeep = new THREE.Group();
  const glass = new THREE.MeshStandardMaterial({ color: 0x9fc4d8, roughness: 0.1, metalness: 0.6 });
  const lamp = new THREE.MeshBasicMaterial({ color: 0xfff4d0 });
  jeep.add(
    box(paint, [4.2, 1.1, 2], [0, 1.05, 0]),
    box(paint, [1.5, 0.35, 1.9], [1.3, 1.75, 0]),
    box(glass, [0.08, 0.75, 1.8], [0.5, 2, 0]),
    box(black, [0.08, 0.08, 1.9], [0.5, 2.4, 0]),
    box(black, [1.9, 0.08, 0.08], [-0.45, 2.45, 0.9]),
    box(black, [1.9, 0.08, 0.08], [-0.45, 2.45, -0.9]),
    box(black, [0.08, 0.9, 0.08], [-1.4, 2, 0.9]),
    box(black, [0.08, 0.9, 0.08], [-1.4, 2, -0.9]),
    box(black, [0.3, 0.35, 2.2], [2.2, 0.75, 0]),
    box(lamp, [0.05, 0.22, 0.3], [2.11, 1.25, 0.7]),
    box(lamp, [0.05, 0.22, 0.3], [2.11, 1.25, -0.7]),
  );
  const spare = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.42, 0.3, 16), black);
  spare.rotation.z = Math.PI / 2;
  spare.position.set(-2.2, 1.3, 0);
  jeep.add(spare);
  const wheels: THREE.Mesh[] = [];
  for (const [x, z] of [
    [-1.4, 1.05],
    [1.4, 1.05],
    [-1.4, -1.05],
    [1.4, -1.05],
  ]) {
    const w = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 0.4, 16), black);
    w.rotation.x = Math.PI / 2;
    w.position.set(x, 0.5, z);
    jeep.add(w);
    wheels.push(w);
  }
  const shade = new THREE.Mesh(
    new THREE.PlaneGeometry(6, 3.4),
    new THREE.MeshBasicMaterial({
      map: glow('rgba(40,20,5,.7)', 'rgba(40,20,5,.45)'),
      transparent: true,
      depthWrite: false,
    }),
  );
  shade.rotation.x = -Math.PI / 2;
  shade.position.y = 0.03;
  jeep.add(shade);
  scene.add(jeep);
  const puff = glow('rgba(243,215,166,.9)', 'rgba(240,207,152,.45)');
  const dust = Array.from({ length: 44 }, () => {
    const s = sprite(puff, [0, 0, 0], 1, { add: false });
    scene.add(s);
    return s;
  });
  const jeepX = (shot: number) => -30 + shot * 12;

  return {
    scene,
    tick({ t, shot }) {
      const x = jeepX(shot);
      jeep.position.set(x, Math.abs(Math.sin(t * 9)) * 0.05, 0);
      jeep.rotation.z = Math.sin(t * 7) * 0.012;
      wheels.forEach((w) => {
        w.rotation.y = -shot * 24;
      });
      dust.forEach((s, i) => {
        // the trail: where the jeep was, older puffs higher, wider and fainter
        const age = i * 0.09 + ((t * 11) % 1) * 0.09;
        s.position.set(jeepX(shot - age) - 2.2, 0.4 + age * 1.1, Math.sin(i * 1.7) * 0.6 * (1 + age));
        s.scale.setScalar(1.2 + age * 5);
        s.material.opacity = Math.max(0, 0.55 * (1 - age / 4));
      });
    },
    cam(i, p, { t, shot }) {
      const x = jeepX(shot);
      if (i === 0) return above({ pos: mix([-16, 18, 58], [-4, 18, 58], p), look: [x, 1, 0], fov: 24 });
      if (i === 1) {
        const hand = [Math.sin(t * 7.3) * 0.05 + Math.sin(t * 13.1) * 0.03, Math.sin(t * 5.1) * 0.04, 0];
        return above({ pos: [x + 5.5 + hand[0], 1.7 + hand[1], 7.5], look: [x - 0.5, 1.1, 0], fov: 42 });
      }
      return above({ pos: [x - lerp(8, 14, p), lerp(2, 38, p), lerp(10, 24, p)], look: [x + 2, 0.8, 0], fov: 45 });
    },
  };
}
