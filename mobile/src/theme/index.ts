// The app's look, after Apple's Human Interface Guidelines: layered greys for depth, one tint colour, the HIG text
// styles, and spring motion. Dark by default, like a video app; light when the phone or Account says so
// (theme/appearance.ts), chosen when the app starts.
import { PixelRatio } from 'react-native';

import { scheme } from './appearance';

export { scheme };

const dark = {
  // Backgrounds, from the page up (Apple's systemBackground, secondary, tertiary, quaternary in dark mode).
  background: '#000000',
  surface: '#1C1C1E',
  surfaceRaised: '#2C2C2E',
  surfacePressed: '#3A3A3C',
  fill: 'rgba(118,118,128,0.24)',
  separator: 'rgba(84,84,88,0.6)',
  border: 'rgba(84,84,88,0.6)',
  // Text.
  text: '#FFFFFF',
  textSecondary: 'rgba(235,235,245,0.6)',
  textMuted: 'rgba(235,235,245,0.45)',
  // The studio's brand: paper white for the main action (Generate), and the blue of the logo's frame as the one tint.
  brand: '#F4F4F4',
  brandEnd: '#DCDCDC',
  onBrand: '#0B0B0B',
  accent: '#8CCBFF',
  onAccent: '#0B0B0B',
  accentSoft: 'rgba(140,203,255,0.16)',
  success: '#30D158',
  successSoft: 'rgba(48,209,88,0.16)',
  warning: '#FF9F0A',
  warningSoft: 'rgba(255,159,10,0.16)',
  danger: '#FF453A',
  dangerSoft: 'rgba(255,69,58,0.16)',
  star: '#FFD60A',
  teal: '#64D2FF',
  pink: '#FF375F',
  // Bars and panels over content.
  chrome: 'rgba(22,22,24,0.94)',
  glass: 'rgba(22,22,24,0.55)',
  scrim: 'rgba(0,0,0,0.5)',
  toast: 'rgba(44,44,46,0.97)',
  segmentThumb: '#636366',
  // The soft gradient behind big cards (credits, "What will you make today?"), and buttons on it.
  heroFrom: '#1B2A38',
  heroTo: '#1C1C1E',
  heroButton: 'rgba(255,255,255,0.08)',
};

const light: typeof dark = {
  background: '#F2F2F7',
  surface: '#FFFFFF',
  surfaceRaised: '#E5E5EA',
  surfacePressed: '#D1D1D6',
  fill: 'rgba(118,118,128,0.12)',
  separator: 'rgba(60,60,67,0.29)',
  border: 'rgba(60,60,67,0.29)',
  text: '#000000',
  // Darker than Apple's own greys and colours, so text keeps a 4.5:1 contrast on white (WCAG AA); faint grey (3:1) is
  // only for chevrons, placeholders and what is switched off.
  textSecondary: '#5C5C63',
  textMuted: '#8A8A90',
  brand: '#111111',
  brandEnd: '#2A2A2A',
  onBrand: '#FFFFFF',
  accent: '#1769B3',
  onAccent: '#FFFFFF',
  accentSoft: 'rgba(23,105,179,0.12)',
  success: '#1E7F36',
  successSoft: 'rgba(30,127,54,0.12)',
  warning: '#B25000',
  warningSoft: 'rgba(178,80,0,0.12)',
  danger: '#D70015',
  dangerSoft: 'rgba(215,0,21,0.1)',
  star: '#FFCC00',
  teal: '#32ADE6',
  pink: '#FF2D55',
  chrome: 'rgba(249,249,249,0.94)',
  glass: 'rgba(249,249,249,0.6)',
  scrim: 'rgba(0,0,0,0.3)',
  toast: 'rgba(255,255,255,0.98)',
  segmentThumb: '#FFFFFF',
  heroFrom: '#DDEEFF',
  heroTo: '#FFFFFF',
  heroButton: 'rgba(0,0,0,0.05)',
};

export const colors = scheme === 'light' ? light : dark;

/** The studio's brand as a soft gradient, for the main button, the avatar and your messages. Text on it is onBrand. */
export const gradient = [colors.brand, colors.brandEnd] as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 32,
} as const;

export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 22,
  pill: 999,
} as const;

// Inter is close to Apple's SF Pro. Android picks the weight by font file, so each style names its file and sets no
// fontWeight; large text is tracked tighter, as SF Pro Display is.
// Three weights only (each file is about 340 KB in the app): small captions are regular, the big credits number bold.
const family = {
  regular: 'Inter_400Regular',
  medium: 'Inter_400Regular',
  semibold: 'Inter_600SemiBold',
  bold: 'Inter_700Bold',
  heavy: 'Inter_700Bold',
} as const;

// The phone's text size, up to twice the normal: line heights grow with it so large text is never cut off.
const scale = Math.min(PixelRatio.getFontScale(), 2);
export const lines = (n: number) => Math.round(n * Math.max(1, scale));

export const fonts = {
  largeTitle: { fontFamily: family.bold, fontSize: 34, lineHeight: lines(41), letterSpacing: -1 },
  title1: { fontFamily: family.bold, fontSize: 28, lineHeight: lines(34), letterSpacing: -0.7 },
  title2: { fontFamily: family.bold, fontSize: 22, lineHeight: lines(28), letterSpacing: -0.5 },
  title3: { fontFamily: family.semibold, fontSize: 20, lineHeight: lines(25), letterSpacing: -0.4 },
  headline: { fontFamily: family.semibold, fontSize: 17, lineHeight: lines(22), letterSpacing: -0.35 },
  body: { fontFamily: family.regular, fontSize: 17, lineHeight: lines(22), letterSpacing: -0.35 },
  callout: { fontFamily: family.regular, fontSize: 16, lineHeight: lines(21), letterSpacing: -0.3 },
  calloutStrong: { fontFamily: family.semibold, fontSize: 16, lineHeight: lines(21), letterSpacing: -0.3 },
  subhead: { fontFamily: family.regular, fontSize: 15, lineHeight: lines(20), letterSpacing: -0.2 },
  subheadStrong: { fontFamily: family.semibold, fontSize: 15, lineHeight: lines(20), letterSpacing: -0.2 },
  footnote: { fontFamily: family.regular, fontSize: 13, lineHeight: lines(18), letterSpacing: -0.08 },
  footnoteStrong: { fontFamily: family.semibold, fontSize: 13, lineHeight: lines(18), letterSpacing: -0.08 },
  caption: { fontFamily: family.medium, fontSize: 12, lineHeight: lines(16), letterSpacing: 0 },
  caption2: { fontFamily: family.semibold, fontSize: 11, lineHeight: lines(13), letterSpacing: 0.06 },
  hero: { fontFamily: family.heavy, fontSize: 48, lineHeight: lines(54), letterSpacing: -1.6 },
} as const;

/** The colour that goes with each kind of work. */
export const kindColors = {
  video: colors.accent,
  image: '#C69CFF',
  audio: '#FF9F0A',
  text: '#30D158',
} as const;

/** Spring motion, for what follows a finger (zoom, switches): quick to answer, settles without any overshoot. */
export const springs = {
  press: { damping: 32, stiffness: 400, mass: 0.6 },
  snappy: { damping: 34, stiffness: 280, mass: 0.8 },
  gentle: { damping: 30, stiffness: 160, mass: 1 },
} as const;

/** Eased timings, for motion that should simply arrive: a press, a sheet, a sliding thumb. */
export const timings = {
  quick: 140,
  normal: 240,
} as const;
