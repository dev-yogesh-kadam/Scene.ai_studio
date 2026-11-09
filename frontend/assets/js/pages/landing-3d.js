// The landing page's sets built in 3D: the four scenes of landing-scenes.js as small worlds of boxes, cylinders and
// light (Three.js, kept in assets/js/vendor), with a real camera for every shot of their plans. The monitor loads this
// only where it can run (WebGL, the full motion setting, a big enough screen) and keeps the drawn set otherwise.
// create(canvas) gives { show(name), shot(i, ms, at), frame(now), size(w, h), pointer(x, y), dispose() }; the page calls
// frame() from its own clock, so nothing renders while the monitor is out of sight.

import * as THREE from '../vendor/three.module.min.js';

const lerp = (a, b, p) => a + (b - a) * p;
const mix = (a, b, p) => a.map((v, i) => lerp(v, b[i], p));
const ease = (p) => (p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2);

function seeded(seed) {
  let s = seed;
  return () => ((s = (s * 9301 + 49297) % 233280) / 233280);
}

function canvasTexture(w, h, draw) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

const gradient = (stops) => canvasTexture(4, 512, (g, w, h) => {
  const l = g.createLinearGradient(0, 0, 0, h);
  stops.forEach(([at, colour]) => l.addColorStop(at, colour));
  g.fillStyle = l; g.fillRect(0, 0, w, h);
});

const glow = (inner, outer) => canvasTexture(256, 256, (g) => {
  const r = g.createRadialGradient(128, 128, 0, 128, 128, 128);
  r.addColorStop(0, inner); r.addColorStop(0.25, outer); r.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = r; g.fillRect(0, 0, 256, 256);
});

function sprite(map, [x, y, z], size, { opacity = 1, add = true } = {}) {
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map, transparent: true, opacity, depthWrite: false, fog: false,
    blending: add ? THREE.AdditiveBlending : THREE.NormalBlending }));
  s.position.set(x, y, z); s.scale.set(size, size, 1);
  return s;
}

function box(material, [w, h, d], [x, y, z]) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material);
  m.position.set(x, y, z);
  return m;
}

// A person of rounded solids, 1.75 tall, with hips and shoulders that swing.
function person(colour) {
  const m = new THREE.MeshStandardMaterial({ color: colour, roughness: 0.8 });
  const g = new THREE.Group();
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.115, 24, 18), m); head.position.y = 1.64; head.scale.set(1, 1.12, 1.02); g.add(head);
  const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.16, 0.42, 6, 16), m); body.position.y = 1.2; body.scale.z = 0.75; g.add(body);
  const limb = (length, r, x, y, tilt = 0) => {
    const pivot = new THREE.Group(); pivot.position.set(x, y, 0); pivot.rotation.z = tilt;
    const part = new THREE.Mesh(new THREE.CapsuleGeometry(r, length, 4, 10), m); part.position.y = -length / 2 - r;
    pivot.add(part); g.add(pivot);
    return pivot;
  };
  g.userData.legs = [limb(0.72, 0.068, -0.09, 0.9), limb(0.72, 0.068, 0.09, 0.9)];
  g.userData.arms = [limb(0.5, 0.048, -0.21, 1.48, -0.08), limb(0.5, 0.048, 0.21, 1.48, 0.08)];
  return g;
}

function stride(who, t, speed, size = 0.7) {
  const [l, r] = who.userData.legs, [a, b] = who.userData.arms, s = Math.sin(t * speed);
  l.rotation.x = s * size; r.rotation.x = -s * size;
  a.rotation.x = -s * size * 0.8; b.rotation.x = s * size * 0.8;
}

// ---------------------------------------------------------------------------------------------------- the four sets
// Each gives its scene, a tick(st) that moves what lives in it, and cam(i, p, st): where shot i's camera is at p (0 to
// 1 through the shot). st has t (seconds of the page), shot (seconds into the shot) and scene (seconds on this set).

function rooftop() {
  const rnd = seeded(7);
  const scene = new THREE.Scene();
  scene.background = gradient([[0, '#1b1640'], [0.45, '#6b2d5c'], [0.72, '#e2694a'], [0.86, '#ffb35c'], [1, '#ffb35c']]);
  scene.fog = new THREE.Fog(0xa84f66, 90, 640);
  scene.add(new THREE.HemisphereLight(0x8a5aa0, 0x150a18, 0.9));
  const sun = new THREE.DirectionalLight(0xffa868, 2.6); sun.position.set(60, 95, -700); scene.add(sun);
  const fill = new THREE.DirectionalLight(0x5a4aa0, 0.4); fill.position.set(-50, 30, 80); scene.add(fill);
  const halo = sprite(glow('rgba(255,243,214,1)', 'rgba(255,190,110,.55)'), [60, 95, -700], 620);
  scene.add(halo, sprite(glow('rgba(255,250,235,1)', 'rgba(255,240,210,.9)'), [60, 95, -698], 70));

  const lit = canvasTexture(64, 128, (g, w, h) => {
    g.fillStyle = '#000'; g.fillRect(0, 0, w, h);
    for (let y = 0; y < 8; y += 1) for (let x = 0; x < 4; x += 1) if (rnd() > 0.62) { g.fillStyle = rnd() > 0.5 ? '#ffc477' : '#ffdca0'; g.fillRect(x * 16 + 4, y * 16 + 5, 8, 7); }
  });
  lit.wrapS = lit.wrapT = THREE.RepeatWrapping;
  for (let i = 0; i < 420; i += 1) {
    const x = (rnd() - 0.5) * 1100, z = -95 - rnd() * 560;
    if (Math.abs(x) < 40 && z > -130) continue;
    const w = 10 + rnd() * 22, d = 10 + rnd() * 22, h = 8 + rnd() * rnd() * 42 + Math.max(0, (-z - 200) / 7) * (0.4 + rnd());
    const windows = lit.clone();
    windows.repeat.set(Math.max(1, Math.round(w / 8)), Math.max(1, Math.round(h / 16)));
    const m = new THREE.MeshStandardMaterial({ color: new THREE.Color().setHSL(0.86, 0.25, 0.07 + rnd() * 0.05), roughness: 0.85,
      emissive: 0xffffff, emissiveIntensity: 1.2, emissiveMap: windows });
    scene.add(box(m, [w, h, d], [x, h / 2 - 30, z]));
    if (rnd() > 0.85) {
      const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.3, 12 + rnd() * 18, 6), m);
      mast.position.set(x, h - 22, z); scene.add(mast);
    }
  }
  // our roof: the parapet, a water tank on legs and the air units
  const dark = new THREE.MeshLambertMaterial({ color: 0x0d0811 });
  scene.add(box(dark, [60, 30, 70], [0, -15, -15]), box(dark, [60, 0.9, 0.4], [0, 0.45, -50]),
    box(dark, [0.4, 0.9, 70], [-30, 0.45, -15]), box(dark, [0.4, 0.9, 70], [30, 0.45, -15]));
  const tank = new THREE.Mesh(new THREE.CylinderGeometry(2.4, 2.4, 4, 24), dark); tank.position.set(-16, 6.5, -47);
  const cap = new THREE.Mesh(new THREE.ConeGeometry(2.7, 1.4, 24), dark); cap.position.set(-16, 9.2, -47);
  scene.add(tank, cap);
  for (const [x, z] of [[-17.6, -48.6], [-14.4, -48.6], [-17.6, -45.4], [-14.4, -45.4]]) {
    const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 4.5, 6), dark); leg.position.set(x, 2.25, z); scene.add(leg);
  }
  scene.add(box(dark, [2.4, 1.4, 1.8], [8, 0.7, -40]), box(dark, [2.4, 1.4, 1.8], [12, 0.7, -40]), box(dark, [2.4, 1.4, 1.8], [-4, 0.7, -44]));
  const her = person(0x0d0811); her.position.set(0.4, 0, -46); her.rotation.y = 0.3; scene.add(her);
  const rim = new THREE.PointLight(0xffb070, 9, 0, 2); rim.position.set(0.9, 1.8, -47.4); scene.add(rim);

  return {
    scene,
    tick({ t }) {
      her.rotation.z = Math.sin(t * 0.8) * 0.015;
      halo.scale.setScalar(620 * (1 + Math.sin(t * 0.6) * 0.04));
    },
    cam(i, p) {
      if (i === 0) return { pos: mix([-1, 1.4, -34], [-1, 1.5, -35.4], p), look: [3, 4, -200], fov: 30 };
      if (i === 1) return { pos: mix([2.2, 1.75, -42.4], [1.6, 1.72, -43.5], p), look: [0.3, 1.5, -46.5], fov: lerp(28, 24, p) };
      return { pos: mix([0, 1.7, -44], [0.6, 2.2, -49], p), look: [40, 60, -650], fov: lerp(40, 16, p) };
    },
  };
}

function neon() {
  const rnd = seeded(11);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x05070f);
  scene.fog = new THREE.FogExp2(0x0b1730, 0.035);
  scene.add(new THREE.HemisphereLight(0x2a3a70, 0x02030a, 1.1));
  const wall = new THREE.MeshStandardMaterial({ color: 0x1a2034, roughness: 0.85 });
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(9, 90), new THREE.MeshStandardMaterial({ color: 0x0a1226, roughness: 0.08, metalness: 0.85 }));
  floor.rotation.x = -Math.PI / 2; floor.position.z = -40; scene.add(floor);
  scene.add(box(wall, [1, 16, 90], [-5, 8, -40]), box(wall, [1, 16, 90], [5, 8, -40]),
    box(new THREE.MeshStandardMaterial({ color: 0x101c38, roughness: 0.9 }), [10, 16, 1], [0, 8, -70]));
  for (let i = 0; i < 26; i += 1) {   // doors, pipes and boxes on the walls
    const side = i % 2 ? 1 : -1;
    scene.add(box(wall, [0.5, 0.6 + rnd() * 1.6, 0.8 + rnd() * 2], [side * 4.3, 1 + rnd() * 9, -4 - rnd() * 60]));
  }
  const pipe = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 90, 8), wall); pipe.rotation.x = Math.PI / 2; pipe.position.set(-4.3, 7.5, -40); scene.add(pipe);
  const signs = [];
  for (const [colour, x, y, z, w, h, d] of [[0xff2e88, -4.45, 4.6, -9, 0.2, 1.1, 3.2], [0x22e3ff, 4.45, 4.2, -16, 0.2, 3.6, 0.9],
    [0xffb02e, 0, 6.2, -69.3, 3.4, 0.6, 0.2], [0xff2e88, 4.45, 7, -34, 0.2, 0.8, 2.4], [0x22e3ff, -4.45, 3, -44, 0.2, 2.2, 0.8]]) {
    const face = new THREE.MeshBasicMaterial({ color: colour });
    scene.add(box(face, [w, h, d], [x, y, z]));
    const light = new THREE.PointLight(colour, 70, 0, 2); light.position.set(x * 0.8, y, z); scene.add(light);
    const c = new THREE.Color(colour), rgba = (a) => `rgba(${Math.round(c.r * 255)},${Math.round(c.g * 255)},${Math.round(c.b * 255)},${a})`;
    const halo = sprite(glow(rgba(0.9), rgba(0.35)), [x * 0.92, y, z], Math.max(h, d) * 3.4, { opacity: 0.8 });
    scene.add(halo);
    signs.push({ face, light, halo, colour, base: light.intensity });
  }
  // rain: streaks in a box twice the height of the alley, slid down and wrapped, so it never runs out
  const streaks = [];
  for (let i = 0; i < 5000; i += 1) {
    const x = (rnd() - 0.5) * 9, y = rnd() * 28, z = 4 - rnd() * 70;
    streaks.push(x, y, z, x - 0.04, y - 0.5, z);
  }
  const rainGeo = new THREE.BufferGeometry(); rainGeo.setAttribute('position', new THREE.Float32BufferAttribute(streaks, 3));
  const rain = new THREE.LineSegments(rainGeo, new THREE.LineBasicMaterial({ color: 0x9fb6ff, transparent: true, opacity: 0.32 }));
  scene.add(rain);
  const runner = person(0x05060c); scene.add(runner);
  const breath = sprite(glow('rgba(220,235,255,.55)', 'rgba(200,220,255,.18)'), [0, 0, 0], 0.6, { add: false });
  const backlight = new THREE.PointLight(0x22e3ff, 0, 0, 2);   // the sign behind the runner, lighting the edges in the close-up
  scene.add(breath, backlight);

  return {
    scene,
    tick({ t, shot }, i) {
      rain.position.y = -((t * 18) % 14);
      const flicker = Math.sin(t * 23) > 0.93 || (t % 5 > 3.1 && t % 5 < 3.25);   // the first pink sign stutters
      signs[0].face.color.setHex(flicker ? 0x40122a : signs[0].colour);
      signs[0].light.intensity = flicker ? 2 : signs[0].base;
      signs[0].halo.material.opacity = flicker ? 0.1 : 0.8;
      if (i < 2) {   // running away down the alley; a new shot starts the run again (the cut hides it)
        runner.position.set(0.9, Math.abs(Math.sin(t * 9)) * 0.06, -6 - shot * 1.7);
        runner.rotation.set(0, -0.25, 0.08);
        stride(runner, t, 9);
        breath.visible = false;
        backlight.intensity = 0;
      } else {       // stopped, turned to the camera, breathing out into the cold
        runner.position.set(0.9, 0, -14);
        runner.rotation.set(0, -0.3, 0);
        backlight.position.set(1.6, 1.9, -15.4); backlight.intensity = 14;
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

function desert() {
  const scene = new THREE.Scene();
  scene.background = gradient([[0, '#5aa9d6'], [0.55, '#bfe0ea'], [0.7, '#f7e3c0'], [1, '#f7e3c0']]);
  scene.fog = new THREE.Fog(0xead2ae, 80, 480);
  scene.add(new THREE.HemisphereLight(0xbfe0ff, 0x8a5a30, 0.9));
  const sun = new THREE.DirectionalLight(0xfff2dd, 3.4); sun.position.set(220, 60, -260); scene.add(sun);
  scene.add(sprite(glow('rgba(255,250,240,1)', 'rgba(255,240,215,.5)'), [180, 120, -500], 160),
    sprite(glow('rgba(255,255,250,1)', 'rgba(255,252,240,.95)'), [180, 120, -499], 30));
  // dunes: a wide sheet lifted by a few waves, flattened along the track the jeep drives (z = 0). The near side, where
  // the cameras stand (z > 0), stays low, so no dune ever comes between a camera and the jeep; the far side is the backdrop.
  const height = (x, z) => {
    const away = Math.min(1, Math.abs(z) / 14);
    return (6 * Math.sin(x * 0.02) + 4 * Math.sin(z * 0.03 + 1) + 2.5 * Math.sin((x + z) * 0.05) + 3) * away * away * (z > 0 ? 0.25 : 1);
  };
  const above = (c) => ({ ...c, pos: [c.pos[0], Math.max(c.pos[1], height(c.pos[0], c.pos[2]) + 1.4), c.pos[2]] });   // never in the sand
  const sand = new THREE.PlaneGeometry(900, 900, 160, 160); sand.rotateX(-Math.PI / 2);
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
  jeep.add(box(paint, [4.2, 1.1, 2], [0, 1.05, 0]), box(paint, [1.5, 0.35, 1.9], [1.3, 1.75, 0]),
    box(glass, [0.08, 0.75, 1.8], [0.5, 2, 0]), box(black, [0.08, 0.08, 1.9], [0.5, 2.4, 0]),
    box(black, [1.9, 0.08, 0.08], [-0.45, 2.45, 0.9]), box(black, [1.9, 0.08, 0.08], [-0.45, 2.45, -0.9]),
    box(black, [0.08, 0.9, 0.08], [-1.4, 2, 0.9]), box(black, [0.08, 0.9, 0.08], [-1.4, 2, -0.9]),
    box(black, [0.3, 0.35, 2.2], [2.2, 0.75, 0]), box(lamp, [0.05, 0.22, 0.3], [2.11, 1.25, 0.7]), box(lamp, [0.05, 0.22, 0.3], [2.11, 1.25, -0.7]));
  const spare = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.42, 0.3, 16), black); spare.rotation.z = Math.PI / 2; spare.position.set(-2.2, 1.3, 0); jeep.add(spare);
  const wheels = [];
  for (const [x, z] of [[-1.4, 1.05], [1.4, 1.05], [-1.4, -1.05], [1.4, -1.05]]) {
    const w = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 0.4, 16), black);
    w.rotation.x = Math.PI / 2; w.position.set(x, 0.5, z); jeep.add(w); wheels.push(w);
  }
  const shade = new THREE.Mesh(new THREE.PlaneGeometry(6, 3.4), new THREE.MeshBasicMaterial({ map: glow('rgba(40,20,5,.7)', 'rgba(40,20,5,.45)'),
    transparent: true, depthWrite: false }));
  shade.rotation.x = -Math.PI / 2; shade.position.y = 0.03; jeep.add(shade);
  scene.add(jeep);
  const puff = glow('rgba(243,215,166,.9)', 'rgba(240,207,152,.45)');
  const dust = Array.from({ length: 44 }, () => { const s = sprite(puff, [0, 0, 0], 1, { add: false }); scene.add(s); return s; });
  const jeepX = (shot) => -30 + shot * 12;

  return {
    scene,
    tick({ t, shot }) {
      const x = jeepX(shot);
      jeep.position.set(x, Math.abs(Math.sin(t * 9)) * 0.05, 0);
      jeep.rotation.z = Math.sin(t * 7) * 0.012;
      wheels.forEach((w) => { w.rotation.y = -shot * 24; });
      dust.forEach((s, i) => {   // the trail: where the jeep was, older puffs higher, wider and fainter
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

function deep() {
  const rnd = seeded(41);
  const scene = new THREE.Scene();
  scene.background = gradient([[0, '#0d4a6b'], [0.5, '#062539'], [1, '#01080f']]);
  scene.fog = new THREE.FogExp2(0x05283d, 0.022);
  scene.add(new THREE.HemisphereLight(0x4fa8d0, 0x020a10, 1));
  // light from the surface: tall soft planes, added on top of what is behind them
  const shaft = canvasTexture(64, 256, (g, w, h) => {
    const l = g.createLinearGradient(0, 0, 0, h);
    l.addColorStop(0, 'rgba(159,232,255,.5)'); l.addColorStop(1, 'rgba(159,232,255,0)');
    g.fillStyle = l; g.fillRect(0, 0, w, h);
    const s = g.createLinearGradient(0, 0, w, 0);
    s.addColorStop(0, 'rgba(0,0,0,1)'); s.addColorStop(0.5, 'rgba(0,0,0,0)'); s.addColorStop(1, 'rgba(0,0,0,1)');
    g.globalCompositeOperation = 'destination-out'; g.fillStyle = s; g.fillRect(0, 0, w, h);
  });
  const rays = [[-8, -0.25, -18], [-1, -0.15, -24], [6, -0.08, -16], [12, -0.2, -30]].map(([x, tilt, z]) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(4, 60), new THREE.MeshBasicMaterial({ map: shaft, transparent: true, depthWrite: false,
      blending: THREE.AdditiveBlending, side: THREE.DoubleSide, fog: false }));
    m.position.set(x, 18, z); m.rotation.z = tilt; scene.add(m);
    return m;
  });
  // marine snow, a box of it twice as tall as needed, sinking and wrapped
  const flakes = [];
  for (let i = 0; i < 1600; i += 1) flakes.push((rnd() - 0.5) * 60, rnd() * 40 - 10, (rnd() - 0.5) * 60);
  const snowGeo = new THREE.BufferGeometry(); snowGeo.setAttribute('position', new THREE.Float32BufferAttribute(flakes, 3));
  const snow = new THREE.Points(snowGeo, new THREE.PointsMaterial({ color: 0xbfefff, size: 0.08, transparent: true, opacity: 0.55 }));
  scene.add(snow);
  // the diver, lying in the water, with a lantern held out ahead
  const suit = new THREE.MeshStandardMaterial({ color: 0x0a1a24, roughness: 0.8 });
  const diver = new THREE.Group();
  const torso = new THREE.Mesh(new THREE.CapsuleGeometry(0.19, 0.75, 6, 14), suit); torso.rotation.z = Math.PI / 2; torso.scale.z = 0.8; diver.add(torso);
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.15, 18, 14), suit); head.position.x = -0.72; diver.add(head);
  const mask = new THREE.Mesh(new THREE.SphereGeometry(0.1, 14, 10), new THREE.MeshStandardMaterial({ color: 0x9fe8ff, roughness: 0.1, metalness: 0.5 }));
  mask.position.set(-0.8, -0.06, 0); mask.scale.set(0.6, 0.7, 1.1); diver.add(mask);
  const tank = new THREE.Mesh(new THREE.CapsuleGeometry(0.11, 0.6, 4, 12), suit); tank.rotation.z = Math.PI / 2; tank.position.set(0, 0.22, 0); diver.add(tank);
  const arm = new THREE.Mesh(new THREE.CapsuleGeometry(0.05, 0.6, 4, 8), suit); arm.rotation.z = Math.PI / 2; arm.position.set(-0.85, -0.12, 0.12); diver.add(arm);
  const fins = [-0.1, 0.1].map((z) => {
    const pivot = new THREE.Group(); pivot.position.set(0.55, 0, z);
    const leg = new THREE.Mesh(new THREE.CapsuleGeometry(0.07, 0.8, 4, 10), suit); leg.rotation.z = Math.PI / 2; leg.position.x = 0.5;
    const fin = box(suit, [0.5, 0.02, 0.3], [1.2, 0, 0]);
    pivot.add(leg, fin); diver.add(pivot);
    return pivot;
  });
  const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.07, 12, 8), new THREE.MeshBasicMaterial({ color: 0xfff2c4 }));
  lamp.position.set(-1.25, -0.1, 0.1); diver.add(lamp);
  const light = new THREE.PointLight(0xffc36b, 18, 0, 2); light.position.copy(lamp.position); diver.add(light);
  const lampGlow = sprite(glow('rgba(255,242,196,1)', 'rgba(255,190,90,.45)'), [-1.25, -0.1, 0.1], 3.2);
  diver.add(lampGlow);
  scene.add(diver);
  const ring = canvasTexture(64, 64, (g) => { g.strokeStyle = 'rgba(200,240,255,.9)'; g.lineWidth = 5; g.beginPath(); g.arc(32, 32, 24, 0, Math.PI * 2); g.stroke(); });
  const bubbleGeo = new THREE.BufferGeometry(); bubbleGeo.setAttribute('position', new THREE.Float32BufferAttribute(new Array(60 * 3).fill(0), 3));
  const bubbles = new THREE.Points(bubbleGeo, new THREE.PointsMaterial({ map: ring, size: 0.14, transparent: true, depthWrite: false }));
  scene.add(bubbles);
  // the whale, far off: a long body, a tail and two fins, in the dark
  const hide = new THREE.MeshStandardMaterial({ color: 0x041722, roughness: 1 });
  const whale = new THREE.Group();
  const bulk = new THREE.Mesh(new THREE.SphereGeometry(1, 32, 16), hide); bulk.scale.set(14, 3.2, 4); whale.add(bulk);
  const tail = box(hide, [2, 0.3, 7], [14.5, 0.6, 0]); tail.rotation.z = 0.2; whale.add(tail);
  for (const z of [-3.4, 3.4]) { const fin = box(hide, [3.5, 0.25, 2.5], [-4, -2, z]); fin.rotation.x = z > 0 ? 0.5 : -0.5; whale.add(fin); }
  scene.add(whale);

  return {
    scene,
    tick({ t, scene: on }) {
      diver.position.set(0, Math.sin(t * 0.9) * 0.15, 0);
      diver.rotation.z = Math.sin(t * 0.9 + 1) * 0.04;
      fins.forEach((f, i) => { f.rotation.z = Math.sin(t * 3 + i * Math.PI) * 0.25; });
      light.intensity = 18 + Math.sin(t * 11) * 1.2;
      snow.position.y = -((t * 0.3) % 20);
      rays.forEach((r, i) => { r.material.opacity = 0.75 + Math.sin(t * 0.5 + i) * 0.25; });
      whale.position.set(14 - on * 0.3, -3, -16);
      tail.rotation.y = Math.sin(t * 0.6) * 0.15;
      const at = bubbleGeo.attributes.position;
      for (let i = 0; i < 60; i += 1) {   // rising from the diver's head, spreading as they go
        const rise = (t * 0.25 + i / 60) % 1;
        at.setXYZ(i, -0.8 + Math.sin(i * 3 + t * 2) * 0.35 * rise, diver.position.y + 0.2 + rise * 12, Math.cos(i * 1.3) * 0.25 * rise);
      }
      at.needsUpdate = true;
    },
    cam(i, p) {
      const d = diver.position;
      if (i === 0) return { pos: mix([-3, 1, 13], [-2.6, 1, 11.5], p), look: [1, 0, -4], fov: 50 };
      if (i === 1) { const a = lerp(-0.9, 0.9, p); return { pos: [d.x + Math.sin(a) * 4.2, d.y + 0.6, d.z + Math.cos(a) * 4.2], look: [d.x - 0.3, d.y, d.z], fov: 40 }; }
      const w = whale.position;
      return { pos: mix([d.x - 0.5, d.y + 0.4, d.z + 3], [-8, 5, 26], p), look: mix([d.x, d.y, d.z], [w.x - 4, w.y, w.z], p), fov: lerp(40, 55, p) };
    },
  };
}

const SETS = { rooftop, neon, desert, deep };

function dispose(scene) {
  scene.traverse((o) => {
    if (o.geometry) o.geometry.dispose();
    for (const m of [].concat(o.material || [])) { for (const v of Object.values(m)) if (v && v.isTexture) v.dispose(); m.dispose(); }
  });
  if (scene.background && scene.background.isTexture) scene.background.dispose();
}

export function create(canvas) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.1;
  const camera = new THREE.PerspectiveCamera(30, 16 / 9, 0.1, 3000);
  let set = null, shot = 0, shotAt = 0, shotMs = 0, sceneAt = 0;
  const lean = { x: 0, y: 0, tx: 0, ty: 0 };

  return {
    show(name) {
      if (set) dispose(set.scene);
      set = SETS[name]();
      shot = 0; shotAt = sceneAt = performance.now(); shotMs = 0;
    },
    shot(i, ms, at = performance.now()) { shot = i; shotAt = at; shotMs = ms; },
    pointer(x, y) { lean.tx = x; lean.ty = y; },
    size(w, h) {
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / h; camera.updateProjectionMatrix();
    },
    frame(now) {
      if (!set) return;
      const st = { t: now / 1000, shot: (now - shotAt) / 1000, scene: (now - sceneAt) / 1000 };
      const p = shotMs ? ease(Math.min(1, (now - shotAt) / shotMs)) : 1;
      set.tick(st, shot);
      const c = set.cam(shot, p, st);
      lean.x += (lean.tx - lean.x) * 0.05; lean.y += (lean.ty - lean.y) * 0.05;   // the mouse leans the camera, softly
      camera.position.set(c.pos[0] + lean.x * 0.35, c.pos[1] - lean.y * 0.18, c.pos[2]);
      camera.lookAt(c.look[0], c.look[1], c.look[2]);
      if (camera.fov !== c.fov) { camera.fov = c.fov; camera.updateProjectionMatrix(); }
      renderer.render(set.scene, camera);
    },
    dispose() {
      if (set) dispose(set.scene);
      set = null;
      renderer.dispose();
    },
  };
}
