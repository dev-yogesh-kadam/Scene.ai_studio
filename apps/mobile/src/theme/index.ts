// The app's look, after Apple's Human Interface Guidelines: layered greys for depth, one tint colour, the HIG text
// styles, and spring motion. Dark by default, like a video app; light when the phone or Account says so
// (theme/appearance.ts), chosen when the app starts.
import { PixelRatio } from 'react-native';

import { dark, light, radius, spacing } from '@scene/shared/tokens/phone';

import { scheme } from './appearance';

export { scheme };

// The colours, spacing and corners come from the shared design tokens (packages/shared/tokens/tokens.json, the notes on
// each palette are there); the text styles and motion are the phone's own, below.
export const colors = scheme === 'light' ? light : dark;

/** The studio's brand as a soft gradient, for the main button, the avatar and your messages. Text on it is onBrand. */
export const gradient = [colors.brand, colors.brandEnd] as const;

export { radius, spacing };

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
