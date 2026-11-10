import { router } from 'expo-router';
import type { ReactNode } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Animated, { Extrapolation, interpolate, useAnimatedScrollHandler, useAnimatedStyle, useSharedValue, type SharedValue } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { IconButton } from './Button';
import { Glass } from './Glass';
import { colors, fonts, spacing } from '@/theme';

const BAR = 44; // the compact bar's height under the status bar, as on iOS

/** The scroll position of a screen's list, and the handler that keeps it. */
export function useScrollY() {
  const scrollY = useSharedValue(0);
  const onScroll = useAnimatedScrollHandler((event) => {
    scrollY.value = event.contentOffset.y;
  });
  return { scrollY, onScroll };
}

/** How far down a list's content starts: below the status bar and the compact bar. */
export function useBarInset() {
  return useSafeAreaInsets().top + BAR;
}

type Props = {
  title: string;
  scrollY: SharedValue<number>;
  /** Buttons at the top right, always visible. */
  actions?: ReactNode;
  /** A back button at the top left, for screens pushed on top of a tab. */
  back?: boolean;
  children: ReactNode;
};

/**
 * A screen with an iOS-style large title. The title scrolls with the list (put <LargeTitle> at its top); once it has
 * gone under, a compact frosted bar fades in with the title small in the middle.
 */
export function TitledScreen({ title, scrollY, actions, back, children }: Props) {
  const insets = useSafeAreaInsets();

  const barStyle = useAnimatedStyle(() => ({ opacity: interpolate(scrollY.value, [10, 44], [0, 1], Extrapolation.CLAMP) }));
  const smallTitle = useAnimatedStyle(() => ({
    opacity: interpolate(scrollY.value, [34, 56], [0, 1], Extrapolation.CLAMP),
    transform: [{ translateY: interpolate(scrollY.value, [34, 56], [6, 0], Extrapolation.CLAMP) }],
  }));

  return (
    <View style={styles.page}>
      {children}
      <View style={[styles.header, { height: insets.top + BAR }]} pointerEvents="box-none">
        <Animated.View style={[StyleSheet.absoluteFill, barStyle]} pointerEvents="none">
          <Glass style={StyleSheet.absoluteFill} />
          <View style={styles.hairline} />
        </Animated.View>
        <View style={[styles.row, { marginTop: insets.top }]} pointerEvents="box-none">
          {back ? (
            <View style={styles.leading}>
              <IconButton icon="chevron-back" label="Back" onPress={() => router.back()} />
            </View>
          ) : null}
          <Animated.Text style={[styles.smallTitle, smallTitle]} numberOfLines={1} importantForAccessibility="no">
            {title}
          </Animated.Text>
          <View style={styles.actions}>{actions}</View>
        </View>
      </View>
    </View>
  );
}

/** The large title at the top of a list. It grows a little when pulled down past the top, as iOS titles do. */
export function LargeTitle({ title, subtitle, scrollY }: { title: string; subtitle?: string; scrollY: SharedValue<number> }) {
  const top = useBarInset();
  const grow = useAnimatedStyle(() => ({
    transform: [{ scale: interpolate(scrollY.value, [-160, 0], [1.12, 1], Extrapolation.CLAMP) }],
  }));
  return (
    <View style={[styles.large, { paddingTop: top - spacing.sm }]}>
      <Animated.Text style={[styles.largeTitle, { transformOrigin: 'left center' }, grow]} numberOfLines={1} accessibilityRole="header">
        {title}
      </Animated.Text>
      {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.background },
  header: { position: 'absolute', top: 0, left: 0, right: 0 },
  hairline: { position: 'absolute', left: 0, right: 0, bottom: 0, height: StyleSheet.hairlineWidth, backgroundColor: colors.separator },
  row: { height: BAR, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingHorizontal: spacing.lg },
  smallTitle: { ...fonts.headline, color: colors.text, maxWidth: '60%' },
  actions: { position: 'absolute', right: spacing.lg, flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  leading: { position: 'absolute', left: spacing.lg },
  large: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
  largeTitle: { ...fonts.largeTitle, color: colors.text },
  subtitle: { ...fonts.subhead, color: colors.textSecondary, marginTop: 2 },
});
