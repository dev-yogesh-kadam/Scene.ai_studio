// The drawn film stills of the landing page: four scenes as SVG, each in colour or as a pencil storyboard sketch. They
// are pictures the studio draws itself, so the page needs no media files. Every scene is drawn as planes at their own
// depth (0 the sky, 1 the lens), so the monitor can move a camera through them (landing-set.js); everywhere else the
// planes are simply laid on top of each other. svg(name, { sketch, id }) gives an <svg> string, viewBox 1600 x 900
// (16:9), filled to its box; planes(name, id) the same scene as its defs and planes; names lists the scenes;
// info(name) their title, the shots of their plan and each shot's camera.
import { DIVER, FIGURE, JEEP, RUNNER, rimmed, skyline, specks, windows } from './sceneParts';
import { classesOf } from '../cx';
import css0 from './Landing5.module.css';
import css1 from './Landing6.module.css';
import css2 from './landingScenes.module.css';
const css = classesOf(css0, css1, css2);

// A shot's camera, from and to over the shot: k zooms in about the point fx, fy (in the drawing's units), px slides
// the camera sideways (near planes move more), f is the depth in focus and b how soft the farthest plane gets.
const cam = (k: number, fx: number, fy: number, f: number, b: number, px = 0) => ({ k, fx, fy, f, b, px });

export type Framing = ReturnType<typeof cam>;
export type ShotCamera = { lens: string; move: string; dur: number; shake?: boolean; from: Framing; to: Framing };
type Scene = {
  title: string;
  shots: string[];
  camera: ShotCamera[];
  defs: (id: string) => string;
  planes: (id: string) => [number, string][];
  sketch: (id: string) => string;
};

const scenes: Record<string, Scene> = {
  rooftop: {
    title: 'Rooftop at dusk',
    shots: ['Wide shot, rooftop at dusk', 'Close-up, she turns to camera', 'Push in on the skyline'],
    camera: [
      {
        lens: '24mm · T2.8',
        move: 'Wide · locked off',
        dur: 6000,
        from: cam(1, 930, 600, 0.82, 2),
        to: cam(1.08, 930, 600, 0.82, 2),
      },
      {
        lens: '85mm · T1.4',
        move: 'Close-up · dolly in',
        dur: 5000,
        from: cam(2.5, 930, 560, 0.82, 12),
        to: cam(3.1, 930, 560, 0.82, 14),
      },
      {
        lens: '50mm · T2.0',
        move: 'Push in on the skyline',
        dur: 7000,
        from: cam(1.3, 1060, 560, 0.35, 8),
        to: cam(2.4, 1060, 560, 0.35, 14),
      },
    ],
    defs: (id) => `
      <linearGradient id="${id}sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1b1640"/><stop offset=".45" stop-color="#6b2d5c"/><stop offset=".72" stop-color="#e2694a"/><stop offset=".86" stop-color="#ffb35c"/></linearGradient>
      <radialGradient id="${id}sun" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#fff3d6"/><stop offset=".25" stop-color="#ffd38a"/><stop offset="1" stop-color="#ff9a4d" stop-opacity="0"/></radialGradient>
      <linearGradient id="${id}haze" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ff9a5c" stop-opacity="0"/><stop offset="1" stop-color="#ff9a5c" stop-opacity=".55"/></linearGradient>
      <linearGradient id="${id}fog" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e27a6a" stop-opacity="0"/><stop offset=".55" stop-color="#c8607a" stop-opacity=".42"/><stop offset="1" stop-color="#c8607a" stop-opacity="0"/></linearGradient>
      <radialGradient id="${id}ray" gradientUnits="userSpaceOnUse" cx="1060" cy="560" r="1100"><stop offset="0" stop-color="#ffd9a0" stop-opacity=".55"/><stop offset="1" stop-color="#ffd9a0" stop-opacity="0"/></radialGradient>
      <filter id="${id}soft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="5"/></filter>`,
    planes: (id) => [
      [
        0,
        `<rect x="-400" y="-300" width="2400" height="1500" fill="url(#${id}sky)"/>
        <circle class="${css('la-a-glow')}" cx="1060" cy="560" r="330" fill="url(#${id}sun)"/><circle cx="1060" cy="560" r="62" fill="#fff1d2"/>`,
      ],
      [
        0.05,
        `<g class="${css('la-a-rays')}" style="mix-blend-mode:screen" opacity=".42">${[
          196, 207, 221, 236, 252, 268, 283, 297, 312, 326, 340,
        ]
          .map((a, i) => {
            const w = i % 2 ? 1.6 : 3.2,
              at = (t: number) =>
                `${(1060 + 1500 * Math.cos((t * Math.PI) / 180)).toFixed(0)} ${(560 + 1500 * Math.sin((t * Math.PI) / 180)).toFixed(0)}`;
            return `<path d="M1060 560 L${at(a - w)} L${at(a + w)} Z" fill="url(#${id}ray)"/>`;
          })
          .join('')}</g>`,
      ],
      [0.15, `<path d="${skyline(640, 7, 150, 70)}" fill="#7a3a5e" opacity=".55"/>`],
      [0.2, `<rect x="-400" y="430" width="2400" height="260" fill="url(#${id}haze)"/>`],
      [0.35, `<path d="${skyline(700, 21, 190, 95)}" fill="#3b1d3f" opacity=".85"/>`],
      [
        0.45,
        `<g class="${css('la-a-fog')}"><rect x="-400" y="560" width="2400" height="240" fill="url(#${id}fog)"/></g>`,
      ],
      [0.55, `<path d="${skyline(770, 3, 170, 140)}" fill="#1c1026"/>${windows(770, 11, 150, 140, '#ffc477')}`],
      [
        0.8,
        `<path d="M-400 760 L2000 744 L2000 1300 L-400 1300 Z" fill="#0d0811"/>
        <path d="M150 744 L150 560 L250 560 L250 744 M138 560 L262 560 L246 520 L154 520 Z M170 744 L176 600 M230 744 L224 600" fill="#0d0811" stroke="#0d0811" stroke-width="10"/>`,
      ],
      [
        0.82,
        `<g class="${css('la-a-sway')}">${rimmed(FIGURE, 930, 750, 1.7, '#0d0811', [
          ['#ffb35c', 2.4, -0.4],
          ['#ffe0b0', 1.2, 0],
        ])}</g>`,
      ],
      [
        1,
        `<g class="${css('la-a-dust')}" filter="url(#${id}soft)">${specks(16, 5, (x, y, r, i) => `<circle cx="${x.toFixed(0)}" cy="${y.toFixed(0)}" r="${(8 + r * 22).toFixed(0)}" fill="#ffd9b0" opacity="${(0.08 + r * 0.16).toFixed(2)}" style="--i:${i}"/>`)}</g>`,
      ],
    ],
    sketch: () => `
      <path d="M0 640 C300 600 1300 610 1600 630"/><circle cx="1060" cy="560" r="62"/>
      <path d="${skyline(700, 21, 190, 95)}"/><path d="${skyline(770, 3, 170, 140)}"/>
      <path d="M0 760 L1600 744"/><path d="M150 744 L150 560 L250 560 L250 744 M138 560 L262 560 L246 520 L154 520 Z"/>
      <g transform="translate(930 750) scale(1.7)"><path d="${FIGURE}"/></g>
      <path d="M820 470 L1060 470 L1060 600 L820 600 Z" stroke-dasharray="14 10"/><path d="M1060 535 L1180 535 M1160 523 L1180 535 L1160 547"/>`,
  },
  neon: {
    title: 'Neon alley',
    shots: ['Low angle, rain on a neon alley', 'Track the runner past the signs', 'Close-up, breath in cold air'],
    camera: [
      {
        lens: '24mm · T1.4',
        move: 'Low angle · creep in',
        dur: 6000,
        from: cam(1, 820, 600, 0.62, 3),
        to: cam(1.07, 820, 600, 0.62, 3),
      },
      {
        lens: '35mm · T1.4',
        move: 'Track with the runner',
        dur: 5500,
        from: cam(1.5, 640, 560, 0.62, 6, -1),
        to: cam(1.5, 1000, 560, 0.62, 6, 1),
      },
      {
        lens: '85mm · T1.2',
        move: 'Close-up · hold',
        dur: 6000,
        from: cam(2.8, 830, 540, 0.62, 12),
        to: cam(3.1, 830, 530, 0.62, 13),
      },
    ],
    defs: (id) => `
      <linearGradient id="${id}bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#05070f"/><stop offset=".6" stop-color="#0b1730"/><stop offset="1" stop-color="#050812"/></linearGradient>
      <filter id="${id}glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="14"/></filter>
      <filter id="${id}wash" x="-50%" y="-80%" width="200%" height="260%"><feGaussianBlur stdDeviation="10 22"/></filter>
      <filter id="${id}far" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="2.5"/></filter>
      <linearGradient id="${id}wet" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0e1a33"/><stop offset="1" stop-color="#03050b"/></linearGradient>
      <radialGradient id="${id}mist" cx=".5" cy=".55" r=".5"><stop offset="0" stop-color="#3a6bd1" stop-opacity=".45"/><stop offset="1" stop-color="#3a6bd1" stop-opacity="0"/></radialGradient>`,
    planes: (id) => [
      [
        0,
        `<rect x="-400" y="-300" width="2400" height="1500" fill="url(#${id}bg)"/><rect x="620" y="300" width="360" height="340" fill="#101c38"/>
        <ellipse class="${css('la-a-glow')}" cx="800" cy="470" rx="420" ry="260" fill="url(#${id}mist)"/>`,
      ],
      [
        0.25,
        `<g filter="url(#${id}far)"><g class="${css('la-a-rain')}" stroke="#9fb6ff" stroke-width="1.5" opacity=".3" stroke-linecap="round">${specks(60, 97, (x, y) => `<path d="M${x.toFixed(0)} ${(y - 60).toFixed(0)} l-7 30"/>`)}</g></g>`,
      ],
      [
        0.3,
        `<g filter="url(#${id}glow)"><rect x="700" y="360" width="200" height="34" fill="#ffb02e"/></g><rect x="700" y="360" width="200" height="34" fill="none" stroke="#ffe7bf" stroke-width="4"/>`,
      ],
      [
        0.5,
        `<path d="M-400 -200 L620 300 L620 640 L-400 1100 Z" fill="#0a0f1e"/><path d="M2000 -200 L980 300 L980 640 L2000 1100 Z" fill="#080c18"/>
        <g class="${css('la-a-flicker')}"><g filter="url(#${id}glow)"><rect x="150" y="220" width="210" height="64" fill="#ff2e88"/></g><rect x="150" y="220" width="210" height="64" fill="none" stroke="#ffd1e6" stroke-width="5"/></g>
        <g filter="url(#${id}glow)"><rect x="1220" y="300" width="70" height="230" fill="#22e3ff"/></g><rect x="1220" y="300" width="70" height="230" fill="none" stroke="#d6fbff" stroke-width="5"/>`,
      ],
      [
        0.6,
        `<path d="M-400 1100 L620 640 L980 640 L2000 1100 Z" fill="url(#${id}wet)"/>
        <g class="${css('la-a-shimmer')}"><g filter="url(#${id}wash)" style="mix-blend-mode:screen"><rect x="150" y="690" width="210" height="190" fill="#ff2e88" opacity=".45"/>
          <rect x="1220" y="650" width="70" height="250" fill="#22e3ff" opacity=".55"/><rect x="700" y="645" width="200" height="70" fill="#ffb02e" opacity=".4"/></g>
          <g stroke-linecap="round" opacity=".7"><path d="M200 760 l120 0 M230 800 l70 0" stroke="#ffb3d4" stroke-width="3"/><path d="M1245 700 l0 140 M1262 720 l0 90" stroke="#bff6ff" stroke-width="3"/></g></g>
        <ellipse class="${css('la-a-ripple')}" cx="830" cy="700" rx="90" ry="10" fill="none" stroke="#9fb6ff" stroke-width="2" opacity=".35"/>`,
      ],
      [
        0.62,
        `<g class="${css('la-a-stride')}">${rimmed(RUNNER, 820, 690, 1.5, '#02030a', [
          ['#22e3ff', 3, 0],
          ['#ff2e88', -2.4, 0],
          ['#d6fbff', 1.4, 0],
        ])}</g>`,
      ],
      [
        1,
        `<g class="${css('la-a-rain near')}" stroke="#9fb6ff" stroke-width="3.5" opacity=".45" stroke-linecap="round">${specks(26, 311, (x, y) => `<path d="M${x.toFixed(0)} ${(y - 90).toFixed(0)} l-20 90"/>`)}</g>`,
      ],
    ],
    sketch: () => `
      <path d="M0 0 L620 300 L620 640 L0 900"/><path d="M1600 0 L980 300 L980 640 L1600 900"/><path d="M620 640 L980 640"/>
      <rect x="150" y="220" width="210" height="64"/><rect x="1220" y="300" width="70" height="230"/><rect x="700" y="360" width="200" height="34"/>
      <g transform="translate(820 690) scale(1.5)"><path d="${RUNNER}"/></g>
      <path d="M1000 600 C1100 560 1200 560 1300 600" stroke-dasharray="14 10"/><path d="M1280 586 L1300 600 L1278 610"/>`,
  },
  desert: {
    title: 'Desert chase',
    shots: ['Extreme wide, dust trail at noon', 'Handheld beside the jeep', 'Crane up over the dunes'],
    camera: [
      {
        lens: '85mm · T5.6',
        move: 'Extreme wide · slow pan',
        dur: 6000,
        from: cam(1, 860, 600, 0.5, 1),
        to: cam(1.06, 960, 600, 0.5, 1),
      },
      {
        lens: '35mm · T2.8',
        move: 'Handheld beside the jeep',
        dur: 5000,
        shake: true,
        from: cam(2.3, 980, 620, 0.5, 8),
        to: cam(2.45, 1000, 615, 0.5, 8),
      },
      {
        lens: '24mm · T4.0',
        move: 'Crane up over the dunes',
        dur: 7000,
        from: cam(1.7, 980, 760, 0.5, 6),
        to: cam(1.15, 980, 420, 0.5, 3),
      },
    ],
    defs: (id) => `
      <linearGradient id="${id}sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5aa9d6"/><stop offset=".55" stop-color="#bfe0ea"/><stop offset=".7" stop-color="#f7e3c0"/></linearGradient>
      <radialGradient id="${id}dust" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#f3d7a6" stop-opacity=".95"/><stop offset="1" stop-color="#f3d7a6" stop-opacity="0"/></radialGradient>`,
    planes: (id) => [
      [
        0,
        `<rect x="-400" y="-300" width="2400" height="1500" fill="url(#${id}sky)"/>
        <circle class="${css('la-a-halo')}" cx="1240" cy="150" r="130" fill="url(#${id}dust)" opacity=".5"/><circle class="${css('la-a-sun')}" cx="1240" cy="150" r="60" fill="#fffaf0"/>`,
      ],
      [
        0.2,
        `<path d="M-400 600 C220 520 420 560 640 530 C900 495 1150 560 2000 510 L2000 1300 L-400 1300 Z" fill="#e9b97a"/>`,
      ],
      [
        0.3,
        `<g class="${css('la-a-heat')}"><ellipse cx="640" cy="640" rx="420" ry="70" fill="url(#${id}dust)"/><ellipse cx="420" cy="620" rx="260" ry="90" fill="url(#${id}dust)" opacity=".8"/></g>`,
      ],
      [
        0.5,
        `<path d="M-400 690 C300 610 520 700 820 640 C1080 590 1300 660 2000 620 L2000 1300 L-400 1300 Z" fill="#d79a5a"/>
        <g class="${css('la-a-trail')}" fill="#f0cf98">${[0, 1, 2, 3, 4].map((i) => `<circle cx="890" cy="640" r="${18 + i * 4}" style="--i:${i}"/>`).join('')}</g>
        <g transform="translate(980 650)"><g class="${css('la-a-car')}">${rimmed(JEEP, 0, 0, 1, '#3a2414', [['#ffe2b0', 1.5, -2.2]])}</g></g>`,
      ],
      [
        0.8,
        `<path d="M-400 800 C260 730 600 820 900 760 C1200 700 1400 780 2000 750 L2000 1300 L-400 1300 Z" fill="#b7733d"/>`,
      ],
      [
        1,
        `<g class="${css('la-a-sand')}" fill="#fff3dc">${Array.from({ length: 26 }, (_, i) => `<circle cx="${(i * 263) % 1600}" cy="${520 + ((i * 97) % 330)}" r="${1.5 + (i % 3)}" style="--i:${i}"/>`).join('')}</g>`,
      ],
    ],
    sketch: () => `
      <circle cx="1240" cy="150" r="60"/><path d="M0 600 C220 520 420 560 640 530 C900 495 1150 560 1600 510"/>
      <path d="M0 690 C300 610 520 700 820 640 C1080 590 1300 660 1600 620"/><path d="M0 800 C260 730 600 820 900 760 C1200 700 1400 780 1600 750"/>
      <g transform="translate(980 650)"><path d="${JEEP}"/></g>
      <path d="M860 640 C700 630 400 640 240 610" stroke-dasharray="10 12"/><path d="M1300 380 L1300 200 M1286 222 L1300 200 L1314 222"/>`,
  },
  deep: {
    title: 'Deep sea',
    shots: ['Wide shot, a lantern in the deep', 'Orbit the diver, bubbles rising', 'Pull back to the whale'],
    camera: [
      {
        lens: '18mm · T2.8',
        move: 'Wide · drift',
        dur: 6000,
        from: cam(1, 930, 420, 0.6, 2),
        to: cam(1.07, 930, 420, 0.6, 2),
      },
      {
        lens: '35mm · T2.0',
        move: 'Orbit the diver',
        dur: 6000,
        from: cam(2.1, 960, 400, 0.6, 9, -1.3),
        to: cam(2.1, 960, 400, 0.6, 9, 1.3),
      },
      {
        lens: '14mm · T2.8',
        move: 'Pull back to the whale',
        dur: 7000,
        from: cam(2.6, 960, 400, 0.6, 10),
        to: cam(1, 1100, 520, 0.3, 4),
      },
    ],
    defs: (id) => `
      <linearGradient id="${id}sea" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0d4a6b"/><stop offset=".5" stop-color="#062539"/><stop offset="1" stop-color="#01080f"/></linearGradient>
      <linearGradient id="${id}ray" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#9fe8ff" stop-opacity=".35"/><stop offset="1" stop-color="#9fe8ff" stop-opacity="0"/></linearGradient>
      <radialGradient id="${id}lamp" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#fff2c4"/><stop offset=".2" stop-color="#ffd27a" stop-opacity=".8"/><stop offset="1" stop-color="#ffb347" stop-opacity="0"/></radialGradient>
      <filter id="${id}soft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="4"/></filter>`,
    planes: (id) => [
      [0, `<rect x="-400" y="-300" width="2400" height="1500" fill="url(#${id}sea)"/>`],
      [
        0.1,
        `<path class="${css('la-a-shafts')}" d="M380 -200 L520 -200 L760 1100 L520 1100 Z M820 -200 L900 -200 L1100 1100 L960 1100 Z M1180 -200 L1260 -200 L1320 1100 L1220 1100 Z" fill="url(#${id}ray)"/>`,
      ],
      [
        0.25,
        `<g class="${css('la-a-whale')}"><path d="M1700 520 C1500 430 1200 420 1000 470 C900 495 860 540 900 570 C960 610 1150 640 1360 620 L1520 690 L1560 640 L1700 650 Z" fill="#03131f" opacity=".9"/></g>`,
      ],
      [
        0.4,
        `<g class="${css('la-a-snow')}" fill="#bfefff" opacity=".35">${specks(70, 41, (x, y, r) => `<circle cx="${x.toFixed(0)}" cy="${y.toFixed(0)}" r="${(1 + r * 1.6).toFixed(1)}"/>`)}</g>`,
      ],
      [
        0.6,
        `<circle class="${css('la-a-glow')}" cx="930" cy="380" r="260" fill="url(#${id}lamp)"/>
        <g class="${css('la-a-bob')}">${rimmed(DIVER, 970, 395, 1.5, '#02090f', [
          ['#ffd27a', 0, -2.5],
          ['#9fe8ff', 0, 2],
        ])}<circle cx="930" cy="376" r="10" fill="#fff6dc"/></g>`,
      ],
      [
        0.65,
        `<g class="${css('la-a-bubbles')}" fill="none" stroke="#bfefff" stroke-width="2" opacity=".55">${Array.from({ length: 22 }, (_, i) => `<circle cx="${1010 + ((i * 37) % 110)}" cy="${330 - i * 16}" r="${3 + (i % 4) * 2}" style="--i:${i}"/>`).join('')}</g>`,
      ],
      [
        1,
        `<g class="${css('la-a-snow near')}" fill="#bfefff" opacity=".22" filter="url(#${id}soft)">${specks(14, 77, (x, y, r) => `<circle cx="${x.toFixed(0)}" cy="${y.toFixed(0)}" r="${(6 + r * 14).toFixed(0)}"/>`)}</g>`,
      ],
    ],
    sketch: () => `
      <path d="M380 0 L760 900 M820 0 L1100 900"/>
      <path d="M1700 520 C1500 430 1200 420 1000 470 C900 495 860 540 900 570 C960 610 1150 640 1360 620 L1520 690 L1560 640 L1700 650"/>
      <g transform="translate(970 395) scale(1.5)"><path d="${DIVER}"/></g><circle cx="930" cy="380" r="40"/>
      <path d="M760 260 C900 160 1100 160 1240 260" stroke-dasharray="14 10"/><path d="M1220 244 L1240 260 L1216 268"/>`,
  },
};

const newId = (name: string) => name + Math.random().toString(36).slice(2, 7);

function svg(name: string, { sketch = false, id = newId(name) }: { sketch?: boolean; id?: string } = {}) {
  const scene = scenes[name];
  if (sketch) {
    return `<svg viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <defs><filter id="${id}pencil"><feTurbulence type="fractalNoise" baseFrequency=".02" numOctaves="2" seed="4"/><feDisplacementMap in="SourceGraphic" scale="9"/></filter></defs>
      <rect width="1600" height="900" fill="#f5f2ea"/>
      <g fill="none" stroke="#3b3a36" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" filter="url(#${id}pencil)" opacity=".85">${scene.sketch(id)}</g>
    </svg>`;
  }
  // flat: the planes on top of each other; on a monitor frame the mouse still leans them by depth (--z, in app.css)
  return `<svg viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <defs>${scene.defs(id)}</defs>${scene
      .planes(id)
      .map(([z, body]) => `<g class="${css('la-a-z')}" style="--z:${z}">${body}</g>`)
      .join('')}</svg>`;
}

// The scene for the monitor's camera: its defs (one <svg> holds them for every plane) and its planes, nearest last.
function planes(name: string, id = newId(name)) {
  const scene = scenes[name];
  return { defs: scene.defs(id), planes: scene.planes(id).map(([z, body]) => ({ z, body })) };
}

export const names = Object.keys(scenes);
export const info = (name: string) => ({
  title: scenes[name].title,
  shots: scenes[name].shots,
  camera: scenes[name].camera,
});
export { svg, planes };
