// The pieces the landing's drawn scenes are made of: silhouettes, a city, lit windows, specks of dust or rain.

export const FIGURE =
  'M0 -118 a13 13 0 1 1 0.1 0 Z M-14 -102 C-22 -98 -24 -80 -24 -62 L-20 -20 L-12 -20 L-10 -54 L-8 -54 L-9 0 L-1 0 L0 -40 L1 -40 L2 0 L10 0 L9 -54 L11 -54 L13 -20 L21 -20 L24 -62 C24 -80 22 -98 14 -102 Z';
export const RUNNER =
  'M6 -112 a12 12 0 1 1 0.1 0 Z M-4 -96 C-14 -90 -18 -70 -16 -56 L-34 -40 L-28 -34 L-10 -48 L-14 -22 L-36 6 L-28 12 L-4 -16 L6 -40 L14 -16 L30 0 L36 -6 L22 -24 L18 -56 L34 -48 L38 -56 L14 -72 C14 -86 8 -96 -4 -96 Z';
export const DIVER =
  'M0 -20 C26 -24 60 -18 86 -6 L120 -14 L126 -4 L94 6 C62 18 26 22 -6 16 C-30 12 -44 4 -44 -4 C-44 -14 -26 -18 0 -20 Z M-44 -4 a14 14 0 1 1 0.1 0 Z';
export const JEEP =
  'M-80 0 L-70 -34 L-30 -40 L-10 -62 L44 -62 L56 -36 L84 -32 L88 0 Z M-67 2 a17 17 0 1 1 34 0 a17 17 0 1 1 -34 0 Z M41 2 a17 17 0 1 1 34 0 a17 17 0 1 1 -34 0 Z';

export function skyline(y: number, seed: number, h: number, w: number) {
  // a row of buildings: a deterministic rhythm, so every page draws the same city
  let x = -20,
    d = 'M-20 900 ',
    last = 900;
  let s = seed;
  const rnd = () => (s = (s * 9301 + 49297) % 233280) / 233280;
  while (x < 1640) {
    const bw = w * (0.5 + rnd());
    const bh = h * (0.35 + rnd() * 0.9);
    d += `L${x.toFixed(0)} ${last.toFixed(0)} L${x.toFixed(0)} ${(y - bh).toFixed(0)} L${(x + bw).toFixed(0)} ${(y - bh).toFixed(0)} `;
    last = y - bh;
    if (rnd() > 0.8) {
      // a mast on the roof
      const m = x + bw * 0.5,
        top = y - bh;
      d += `L${(m - 3).toFixed(0)} ${top.toFixed(0)} L${(m - 3).toFixed(0)} ${(top - 34 - rnd() * 40).toFixed(0)} L${(m + 3).toFixed(0)} ${(top - 34 - rnd() * 40).toFixed(0)} L${(m + 3).toFixed(0)} ${top.toFixed(0)} `;
    }
    x += bw + rnd() * 6;
  }
  return d + 'L1640 900 Z';
}

export function windows(y: number, seed: number, h: number, w: number, colour: string) {
  // lit windows on the near buildings: a few warm squares, the same on every page
  let s = seed,
    out = '';
  const rnd = () => (s = (s * 9301 + 49297) % 233280) / 233280;
  for (let i = 0; i < 90; i += 1) {
    const x = rnd() * 1600,
      top = y - h * (0.15 + rnd() * 0.6);
    if (rnd() > 0.45)
      out += `<rect x="${x.toFixed(0)}" y="${top.toFixed(0)}" width="${(w * 0.05 + 4).toFixed(0)}" height="7" fill="${colour}" opacity="${(0.35 + rnd() * 0.6).toFixed(2)}"/>`;
  }
  return out;
}

// A silhouette lit from behind: copies of its shape in the light's colours, a little off to the lit side, under it.
export function rimmed(
  path: string,
  x: number,
  y: number,
  scale: number,
  fill: string,
  rims: [string, number, number][],
) {
  return `<g transform="translate(${x} ${y}) scale(${scale})">${rims.map(([colour, dx, dy]) => `<path d="${path}" fill="${colour}" transform="translate(${dx} ${dy})"/>`).join('')}<path d="${path}" fill="${fill}"/></g>`;
}

// Specks of dust, snow or rain at one depth: the same every time, from a seed.
export function specks(n: number, seed: number, draw: (x: number, y: number, r: number, i: number) => string) {
  let s = seed,
    out = '';
  const rnd = () => (s = (s * 9301 + 49297) % 233280) / 233280;
  for (let i = 0; i < n; i += 1) out += draw(rnd() * 1600, rnd() * 900, rnd(), i);
  return out;
}
