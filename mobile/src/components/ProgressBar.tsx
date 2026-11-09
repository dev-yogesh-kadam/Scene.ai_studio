import { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, { Easing, useAnimatedStyle, useSharedValue, withRepeat, withTiming } from 'react-native-reanimated';

import { colors, radius } from '@/theme';

/** A thin bar that springs to `value` (0 to 1). Without a value it sweeps: running, progress not known yet. */
export function ProgressBar({ value, color = colors.accent }: { value: number | null; color?: string }) {
  const width = useSharedValue(value ?? 0);
  const sweep = useSharedValue(0);

  useEffect(() => {
    if (value != null) width.value = withTiming(Math.max(0.03, Math.min(1, value)), { duration: 500, easing: Easing.out(Easing.cubic) });
  }, [value, width]);
  useEffect(() => {
    sweep.value = value == null ? withRepeat(withTiming(1, { duration: 1400, easing: Easing.inOut(Easing.cubic) }), -1) : 0;
  }, [value, sweep]);

  const fill = useAnimatedStyle(() => ({ width: `${width.value * 100}%` }));
  const moving = useAnimatedStyle(() => ({ left: `${-35 + sweep.value * 135}%` }));

  return (
    <View style={styles.track}>
      {value == null ? (
        <Animated.View style={[styles.fill, styles.sweep, { backgroundColor: color }, moving]} />
      ) : (
        <Animated.View style={[styles.fill, { backgroundColor: color }, fill]} />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  track: { height: 4, borderRadius: radius.pill, backgroundColor: colors.fill, overflow: 'hidden' },
  fill: { height: '100%', borderRadius: radius.pill },
  sweep: { position: 'absolute', width: '35%' },
});
