// The deep sea, in 3D: light from the surface, the diver and the lantern, and a whale far off.

import * as THREE from 'three';
import { box, canvasTexture, glow, gradient, lerp, mix, seeded, sprite, type Set3D } from './kit';

export function deep(): Set3D {
  const rnd = seeded(41);
  const scene = new THREE.Scene();
  scene.background = gradient([
    [0, '#0d4a6b'],
    [0.5, '#062539'],
    [1, '#01080f'],
  ]);
  scene.fog = new THREE.FogExp2(0x05283d, 0.022);
  scene.add(new THREE.HemisphereLight(0x4fa8d0, 0x020a10, 1));
  // light from the surface: tall soft planes, added on top of what is behind them
  const shaft = canvasTexture(64, 256, (g, w, h) => {
    const l = g.createLinearGradient(0, 0, 0, h);
    l.addColorStop(0, 'rgba(159,232,255,.5)');
    l.addColorStop(1, 'rgba(159,232,255,0)');
    g.fillStyle = l;
    g.fillRect(0, 0, w, h);
    const s = g.createLinearGradient(0, 0, w, 0);
    s.addColorStop(0, 'rgba(0,0,0,1)');
    s.addColorStop(0.5, 'rgba(0,0,0,0)');
    s.addColorStop(1, 'rgba(0,0,0,1)');
    g.globalCompositeOperation = 'destination-out';
    g.fillStyle = s;
    g.fillRect(0, 0, w, h);
  });
  const rays = [
    [-8, -0.25, -18],
    [-1, -0.15, -24],
    [6, -0.08, -16],
    [12, -0.2, -30],
  ].map(([x, tilt, z]) => {
    const m = new THREE.Mesh(
      new THREE.PlaneGeometry(4, 60),
      new THREE.MeshBasicMaterial({
        map: shaft,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        side: THREE.DoubleSide,
        fog: false,
      }),
    );
    m.position.set(x, 18, z);
    m.rotation.z = tilt;
    scene.add(m);
    return m;
  });
  // marine snow, a box of it twice as tall as needed, sinking and wrapped
  const flakes: number[] = [];
  for (let i = 0; i < 1600; i += 1) flakes.push((rnd() - 0.5) * 60, rnd() * 40 - 10, (rnd() - 0.5) * 60);
  const snowGeo = new THREE.BufferGeometry();
  snowGeo.setAttribute('position', new THREE.Float32BufferAttribute(flakes, 3));
  const snow = new THREE.Points(
    snowGeo,
    new THREE.PointsMaterial({ color: 0xbfefff, size: 0.08, transparent: true, opacity: 0.55 }),
  );
  scene.add(snow);
  // the diver, lying in the water, with a lantern held out ahead
  const suit = new THREE.MeshStandardMaterial({ color: 0x0a1a24, roughness: 0.8 });
  const diver = new THREE.Group();
  const torso = new THREE.Mesh(new THREE.CapsuleGeometry(0.19, 0.75, 6, 14), suit);
  torso.rotation.z = Math.PI / 2;
  torso.scale.z = 0.8;
  diver.add(torso);
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.15, 18, 14), suit);
  head.position.x = -0.72;
  diver.add(head);
  const mask = new THREE.Mesh(
    new THREE.SphereGeometry(0.1, 14, 10),
    new THREE.MeshStandardMaterial({ color: 0x9fe8ff, roughness: 0.1, metalness: 0.5 }),
  );
  mask.position.set(-0.8, -0.06, 0);
  mask.scale.set(0.6, 0.7, 1.1);
  diver.add(mask);
  const tank = new THREE.Mesh(new THREE.CapsuleGeometry(0.11, 0.6, 4, 12), suit);
  tank.rotation.z = Math.PI / 2;
  tank.position.set(0, 0.22, 0);
  diver.add(tank);
  const arm = new THREE.Mesh(new THREE.CapsuleGeometry(0.05, 0.6, 4, 8), suit);
  arm.rotation.z = Math.PI / 2;
  arm.position.set(-0.85, -0.12, 0.12);
  diver.add(arm);
  const fins = [-0.1, 0.1].map((z) => {
    const pivot = new THREE.Group();
    pivot.position.set(0.55, 0, z);
    const leg = new THREE.Mesh(new THREE.CapsuleGeometry(0.07, 0.8, 4, 10), suit);
    leg.rotation.z = Math.PI / 2;
    leg.position.x = 0.5;
    const fin = box(suit, [0.5, 0.02, 0.3], [1.2, 0, 0]);
    pivot.add(leg, fin);
    diver.add(pivot);
    return pivot;
  });
  const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.07, 12, 8), new THREE.MeshBasicMaterial({ color: 0xfff2c4 }));
  lamp.position.set(-1.25, -0.1, 0.1);
  diver.add(lamp);
  const light = new THREE.PointLight(0xffc36b, 18, 0, 2);
  light.position.copy(lamp.position);
  diver.add(light);
  const lampGlow = sprite(glow('rgba(255,242,196,1)', 'rgba(255,190,90,.45)'), [-1.25, -0.1, 0.1], 3.2);
  diver.add(lampGlow);
  scene.add(diver);
  const ring = canvasTexture(64, 64, (g) => {
    g.strokeStyle = 'rgba(200,240,255,.9)';
    g.lineWidth = 5;
    g.beginPath();
    g.arc(32, 32, 24, 0, Math.PI * 2);
    g.stroke();
  });
  const bubbleGeo = new THREE.BufferGeometry();
  bubbleGeo.setAttribute('position', new THREE.Float32BufferAttribute(new Array<number>(60 * 3).fill(0), 3));
  const bubbles = new THREE.Points(
    bubbleGeo,
    new THREE.PointsMaterial({ map: ring, size: 0.14, transparent: true, depthWrite: false }),
  );
  scene.add(bubbles);
  // the whale, far off: a long body, a tail and two fins, in the dark
  const hide = new THREE.MeshStandardMaterial({ color: 0x041722, roughness: 1 });
  const whale = new THREE.Group();
  const bulk = new THREE.Mesh(new THREE.SphereGeometry(1, 32, 16), hide);
  bulk.scale.set(14, 3.2, 4);
  whale.add(bulk);
  const tail = box(hide, [2, 0.3, 7], [14.5, 0.6, 0]);
  tail.rotation.z = 0.2;
  whale.add(tail);
  for (const z of [-3.4, 3.4]) {
    const fin = box(hide, [3.5, 0.25, 2.5], [-4, -2, z]);
    fin.rotation.x = z > 0 ? 0.5 : -0.5;
    whale.add(fin);
  }
  scene.add(whale);

  return {
    scene,
    tick({ t, scene: on }) {
      diver.position.set(0, Math.sin(t * 0.9) * 0.15, 0);
      diver.rotation.z = Math.sin(t * 0.9 + 1) * 0.04;
      fins.forEach((f, i) => {
        f.rotation.z = Math.sin(t * 3 + i * Math.PI) * 0.25;
      });
      light.intensity = 18 + Math.sin(t * 11) * 1.2;
      snow.position.y = -((t * 0.3) % 20);
      rays.forEach((r, i) => {
        r.material.opacity = 0.75 + Math.sin(t * 0.5 + i) * 0.25;
      });
      whale.position.set(14 - on * 0.3, -3, -16);
      tail.rotation.y = Math.sin(t * 0.6) * 0.15;
      const at = bubbleGeo.attributes.position;
      for (let i = 0; i < 60; i += 1) {
        // rising from the diver's head, spreading as they go
        const rise = (t * 0.25 + i / 60) % 1;
        at.setXYZ(
          i,
          -0.8 + Math.sin(i * 3 + t * 2) * 0.35 * rise,
          diver.position.y + 0.2 + rise * 12,
          Math.cos(i * 1.3) * 0.25 * rise,
        );
      }
      at.needsUpdate = true;
    },
    cam(i, p) {
      const d = diver.position;
      if (i === 0) return { pos: mix([-3, 1, 13], [-2.6, 1, 11.5], p), look: [1, 0, -4], fov: 50 };
      if (i === 1) {
        const a = lerp(-0.9, 0.9, p);
        return {
          pos: [d.x + Math.sin(a) * 4.2, d.y + 0.6, d.z + Math.cos(a) * 4.2],
          look: [d.x - 0.3, d.y, d.z],
          fov: 40,
        };
      }
      const w = whale.position;
      return {
        pos: mix([d.x - 0.5, d.y + 0.4, d.z + 3], [-8, 5, 26], p),
        look: mix([d.x, d.y, d.z], [w.x - 4, w.y, w.z], p),
        fov: lerp(40, 55, p),
      };
    },
  };
}
