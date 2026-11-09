import { Image } from 'expo-image';
import { StyleSheet } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, { runOnJS, useAnimatedStyle, useSharedValue, withSpring } from 'react-native-reanimated';

import { springs } from '@/theme';

type Source = { uri: string; headers?: Record<string, string> };

/**
 * A picture you can pinch to zoom, drag around while zoomed, and double-tap to zoom in or back out, as in Photos.
 * `onZoomed` says whether it is zoomed, so a swipe to the next item can wait until it isn't.
 */
export function ZoomImage({ source, placeholder, onZoomed, onTap }: { source: Source; placeholder?: Source; onZoomed?: (zoomed: boolean) => void; onTap?: () => void }) {
  const scale = useSharedValue(1);
  const saved = useSharedValue(1);
  const x = useSharedValue(0);
  const y = useSharedValue(0);
  const savedX = useSharedValue(0);
  const savedY = useSharedValue(0);

  const tell = (zoomed: boolean) => onZoomed?.(zoomed);
  const reset = () => {
    'worklet';
    scale.value = withSpring(1, springs.snappy);
    saved.value = 1;
    x.value = withSpring(0, springs.snappy);
    y.value = withSpring(0, springs.snappy);
    savedX.value = 0;
    savedY.value = 0;
    runOnJS(tell)(false);
  };

  const pinch = Gesture.Pinch()
    .onUpdate((e) => {
      scale.value = Math.max(0.8, Math.min(saved.value * e.scale, 5));
    })
    .onEnd(() => {
      if (scale.value <= 1.02) reset();
      else {
        saved.value = scale.value;
        runOnJS(tell)(true);
      }
    });

  const pan = Gesture.Pan()
    .minPointers(1)
    .onUpdate((e) => {
      if (saved.value <= 1) return;   // not zoomed: the swipe belongs to the player (next / previous)
      x.value = savedX.value + e.translationX;
      y.value = savedY.value + e.translationY;
    })
    .onEnd(() => {
      savedX.value = x.value;
      savedY.value = y.value;
    });

  const doubleTap = Gesture.Tap()
    .numberOfTaps(2)
    .onEnd(() => {
      if (saved.value > 1) reset();
      else {
        scale.value = withSpring(2.5, springs.snappy);
        saved.value = 2.5;
        runOnJS(tell)(true);
      }
    });

  const singleTap = Gesture.Tap()
    .numberOfTaps(1)
    .requireExternalGestureToFail(doubleTap)
    .onEnd(() => {
      if (onTap) runOnJS(onTap)();
    });

  const style = useAnimatedStyle(() => ({ transform: [{ translateX: x.value }, { translateY: y.value }, { scale: scale.value }] }));

  return (
    <GestureDetector gesture={Gesture.Simultaneous(pinch, pan, Gesture.Exclusive(doubleTap, singleTap))}>
      <Animated.View style={[StyleSheet.absoluteFill, style]}>
        <Image source={source} placeholder={placeholder} style={StyleSheet.absoluteFill} contentFit="contain" transition={300} />
      </Animated.View>
    </GestureDetector>
  );
}
