// What the app's native side does on a phone, done by stand-ins in tests: animations (jest.reanimated.js) and gestures.
jest.mock('react-native-reanimated', () => require('./jest.reanimated'));
jest.mock('react-native-worklets', () => ({}));
require('react-native-gesture-handler/jestSetup');
