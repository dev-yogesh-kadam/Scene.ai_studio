// The studio's line icons (24px grid, drawn in the text colour), as data: each is a list of [element, attributes].

import type { IconPart } from './icons';

export const ICONS_A = {
  home: [
    [
      'path',
      {
        d: 'M4 10.5 12 4l8 6.5V20H4z',
      },
    ],
    [
      'path',
      {
        d: 'M9.5 20v-6h5v6',
      },
    ],
  ],
  folder: [
    [
      'path',
      {
        d: 'M3.5 5.5h6l2 2.5h9v10.5h-17z',
      },
    ],
  ],
  play: [
    [
      'path',
      {
        d: 'M7.5 5v14l11-7z',
      },
    ],
  ],
  pause: [
    [
      'path',
      {
        d: 'M8 5v14M16 5v14',
      },
    ],
  ],
  grid: [
    [
      'path',
      {
        d: 'M3.5 3.5h7v7h-7zM13.5 3.5h7v7h-7zM3.5 13.5h7v7h-7zM13.5 13.5h7v7h-7z',
      },
    ],
  ],
  sliders: [
    [
      'path',
      {
        d: 'M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1',
      },
    ],
    [
      'path',
      {
        d: 'M13 4h4v4h-4zM7 10h4v4H7zM15 16h4v4h-4z',
      },
    ],
  ],
  shield: [
    [
      'path',
      {
        d: 'M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6z',
      },
    ],
  ],
  logout: [
    [
      'path',
      {
        d: 'M15 4h5v16h-5',
      },
    ],
    [
      'path',
      {
        d: 'M10 8l-4 4 4 4M6 12h10',
      },
    ],
  ],
  check: [
    [
      'path',
      {
        d: 'M5 12.5l4.5 4.5L19 7.5',
      },
    ],
  ],
  chevron: [
    [
      'path',
      {
        d: 'M8 10l4-4 4 4M8 14l4 4 4-4',
      },
    ],
  ],
  pencil: [
    [
      'path',
      {
        d: 'M14.5 5.5l4 4L8 20H4v-4z',
      },
    ],
  ],
  trash: [
    [
      'path',
      {
        d: 'M4.5 7h15M9.5 7V4.5h5V7M6.5 7l.8 13h9.4l.8-13',
      },
    ],
  ],
  chat: [
    [
      'path',
      {
        d: 'M4 5h16v11H10l-5 4v-4H4z',
      },
    ],
  ],
  memory: [
    [
      'path',
      {
        d: 'M12 3.5 3.5 8 12 12.5 20.5 8z',
      },
    ],
    [
      'path',
      {
        d: 'M3.5 12 12 16.5 20.5 12',
      },
    ],
    [
      'path',
      {
        d: 'M3.5 16 12 20.5 20.5 16',
      },
    ],
  ],
  server: [
    [
      'path',
      {
        d: 'M4 4.5h16v6H4zM4 13.5h16v6H4z',
      },
    ],
    [
      'path',
      {
        d: 'M7.5 7.5h.01M7.5 16.5h.01',
      },
    ],
  ],
  bolt: [
    [
      'path',
      {
        d: 'M13 3 5 13.5h6L10 21l9-11h-6z',
      },
    ],
  ],
  back: [
    [
      'path',
      {
        d: 'M14.5 6 8.5 12l6 6',
      },
    ],
  ],
  plus: [
    [
      'path',
      {
        d: 'M12 5v14M5 12h14',
      },
    ],
  ],
  image: [
    [
      'path',
      {
        d: 'M4 5h16v14H4z',
      },
    ],
    [
      'path',
      {
        d: 'M4 16l4.5-4.5 4 4 2.5-2.5 5 5',
      },
    ],
    [
      'circle',
      {
        cx: '15.5',
        cy: '9.5',
        r: '1.5',
      },
    ],
  ],
  video: [
    [
      'path',
      {
        d: 'M3.5 6h12v12h-12z',
      },
    ],
    [
      'path',
      {
        d: 'M15.5 10.5 20.5 8v8l-5-2.5',
      },
    ],
  ],
  music: [
    [
      'path',
      {
        d: 'M9 17.5V5.5l10-2v12',
      },
    ],
    [
      'circle',
      {
        cx: '6.5',
        cy: '17.5',
        r: '2.5',
      },
    ],
    [
      'circle',
      {
        cx: '16.5',
        cy: '15.5',
        r: '2.5',
      },
    ],
  ],
  audio: [
    [
      'path',
      {
        d: 'M5 10v4M9 6v12M13 9v6M17 4v16M21 10v4',
      },
    ],
  ],
  title: [
    [
      'path',
      {
        d: 'M5 7V5h14v2M12 5v14M9 19h6',
      },
    ],
  ],
  upscale: [
    [
      'path',
      {
        d: 'M14 4h6v6M20 4l-7 7M10 20H4v-6M4 20l7-7',
      },
    ],
  ],
  hand: [
    [
      'path',
      {
        d: 'M8 12V6.5a1.5 1.5 0 0 1 3 0V11M11 10.5V5a1.5 1.5 0 0 1 3 0v5.5M14 10.5V6.5a1.5 1.5 0 0 1 3 0V14c0 3.6-2.4 6.5-6 6.5-2.6 0-4.2-1.4-5.4-3.6L4 13.5a1.4 1.4 0 0 1 2.3-1.6L8 14',
      },
    ],
  ],
  handvideo: [
    [
      'path',
      {
        d: 'M7 13V7.5a1.4 1.4 0 0 1 2.8 0V11M9.8 10.5V6a1.4 1.4 0 0 1 2.8 0v5M12.6 11V8a1.4 1.4 0 0 1 2.8 0v6c0 3.3-2.2 6-5.5 6-2.4 0-3.8-1.3-4.9-3.3L3.5 14a1.3 1.3 0 0 1 2.1-1.5L7 14.5',
      },
    ],
    [
      'path',
      {
        d: 'M17 4.5h3.5v3H17zM20.5 5.2 22 4.5v3l-1.5-.7',
      },
    ],
  ],
  forward: [
    [
      'path',
      {
        d: 'M4 6.5v11l7-5.5zM12.5 6.5v11l7-5.5z',
      },
    ],
  ],
  clock: [
    [
      'circle',
      {
        cx: '12',
        cy: '12',
        r: '8.5',
      },
    ],
    [
      'path',
      {
        d: 'M12 7.5V12l3 2',
      },
    ],
  ],
  frame: [
    [
      'path',
      {
        d: 'M8 3.5v17M16 3.5v17M3.5 8h17M3.5 16h17',
      },
    ],
  ],
  gem: [
    [
      'path',
      {
        d: 'M7 4.5h10l3.5 5L12 20 3.5 9.5z',
      },
    ],
    [
      'path',
      {
        d: 'M3.5 9.5h17M9.5 4.5 8 9.5l4 10.5 4-10.5-1.5-5',
      },
    ],
  ],
  bars: [
    [
      'path',
      {
        d: 'M5 20V10M9.5 20V6M14 20v-8M18.5 20V4',
      },
    ],
  ],
  expand: [
    [
      'path',
      {
        d: 'M14 4h6v6M20 4l-6 6M10 20H4v-6M4 20l6-6',
      },
    ],
  ],
  shrink: [
    [
      'path',
      {
        d: 'M20 10h-6V4M14 10l6-6M4 14h6v6M10 14l-6 6',
      },
    ],
  ],
  arrowup: [
    [
      'path',
      {
        d: 'M12 19V5M6 11l6-6 6 6',
      },
    ],
  ],
} satisfies Record<string, IconPart[]>;
