// A stand-in for react-native-reanimated in tests: plain views, values that jump straight to where they are going, and
// entrance animations that do nothing. Only what the app uses. (Reanimated 4's own mock needs its native side.)
const React = require('react');
const { View, Text, ScrollView, FlatList, Image } = require('react-native');

const passThrough = (Component) => React.forwardRef((props, ref) => React.createElement(Component, { ...props, ref }));

// An entrance or layout builder: every chained call (.duration(200), .delay(…)) gives the builder back.
const builder = () => {
  const b = new Proxy(function () {}, { get: (_, key) => (key === 'build' ? () => ({}) : () => b), apply: () => b });
  return b;
};

const identity = (value) => value;
const Easing = new Proxy({}, { get: () => (...args) => (args.length && typeof args[0] === 'function' ? args[0] : identity) });

const Animated = {
  View: passThrough(View),
  Text: passThrough(Text),
  ScrollView: passThrough(ScrollView),
  FlatList: passThrough(FlatList),
  Image: passThrough(Image),
  createAnimatedComponent: passThrough,
};

module.exports = {
  __esModule: true,
  default: Animated,
  ...Animated,
  useSharedValue: (value) => React.useRef({ value }).current,
  useDerivedValue: (fn) => ({ value: fn() }),
  useAnimatedStyle: (fn) => fn(),
  useAnimatedScrollHandler: () => () => {},
  withTiming: identity,
  withSpring: identity,
  withRepeat: identity,
  withSequence: (...values) => values[values.length - 1],
  interpolate: (_value, _input, output) => output[output.length - 1],
  interpolateColor: (_value, _input, output) => output[output.length - 1],
  runOnJS: (fn) => fn,
  Extrapolation: { CLAMP: 'clamp', EXTEND: 'extend', IDENTITY: 'identity' },
  Easing,
  FadeIn: builder(),
  FadeOut: builder(),
  FadeOutUp: builder(),
  LinearTransition: builder(),
};
