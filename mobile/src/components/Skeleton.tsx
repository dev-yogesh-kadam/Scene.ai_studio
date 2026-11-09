import { useEffect } from 'react';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';
import Animated, { Easing, useAnimatedStyle, useSharedValue, withRepeat, withTiming } from 'react-native-reanimated';

import { colors, radius, spacing } from '@/theme';

/** A grey shape that breathes while the real content loads, so the screen keeps its layout. */
export function Skeleton({ style }: { style?: StyleProp<ViewStyle> }) {
  const glow = useSharedValue(0.5);
  useEffect(() => {
    glow.value = withRepeat(withTiming(1, { duration: 900, easing: Easing.inOut(Easing.quad) }), -1, true);
  }, [glow]);
  const breathe = useAnimatedStyle(() => ({ opacity: glow.value }));
  return <Animated.View style={[styles.bone, style, breathe]} />;
}

/** Placeholders shaped like job cards. */
export function JobSkeletons() {
  return (
    <View style={{ gap: spacing.md }}>
      {[0, 1, 2].map((i) => (
        <View key={i} style={styles.card}>
          <Skeleton style={styles.thumb} />
          <View style={{ flex: 1, gap: 8 }}>
            <Skeleton style={{ height: 16, width: '60%' }} />
            <Skeleton style={{ height: 12, width: '90%' }} />
            <Skeleton style={{ height: 12, width: '40%' }} />
          </View>
        </View>
      ))}
    </View>
  );
}

/** Placeholders shaped like the library grid. */
export function GridSkeletons() {
  return (
    <View style={styles.grid}>
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <View key={i} style={styles.tile}>
          <Skeleton style={styles.tileImage} />
          <Skeleton style={{ height: 12, width: '70%', marginTop: 8 }} />
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  bone: { backgroundColor: colors.surfaceRaised, borderRadius: 6 },
  card: { flexDirection: 'row', gap: spacing.md, backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.md },
  thumb: { width: 64, height: 64, borderRadius: radius.md },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md, paddingHorizontal: spacing.lg },
  tile: { width: '47.5%' },
  tileImage: { aspectRatio: 1, borderRadius: radius.md },
});
