import * as Haptics from '@/lib/haptics';
import type { ReactNode } from 'react';
import { Pressable, type PressableProps, type StyleProp, type ViewStyle } from 'react-native';
import Animated, { Easing, useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';

import { timings } from '@/theme';

const ease = Easing.out(Easing.quad);

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

type Props = Omit<PressableProps, 'style' | 'children'> & {
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
  /** How far it sinks when pressed (1 = not at all). */
  scaleTo?: number;
  /** A light tap felt on press. */
  haptic?: 'light' | 'selection' | false;
};

/** Anything tappable: it sinks a little under the finger and eases back, as on iOS. */
export function Tap({ children, style, scaleTo = 0.97, haptic = false, onPressIn, onPressOut, onPress, disabled, ...rest }: Props) {
  const scale = useSharedValue(1);
  const pressed = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));
  return (
    <AnimatedPressable
      accessibilityRole={onPress ? 'button' : undefined}
      {...rest}
      disabled={disabled}
      accessibilityState={{ disabled: !!disabled, ...rest.accessibilityState }}
      onPressIn={(event) => {
        scale.value = withTiming(scaleTo, { duration: 90, easing: ease });
        onPressIn?.(event);
      }}
      onPressOut={(event) => {
        scale.value = withTiming(1, { duration: timings.quick, easing: ease });
        onPressOut?.(event);
      }}
      onPress={(event) => {
        if (haptic === 'light') void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
        if (haptic === 'selection') void Haptics.selectionAsync();
        onPress?.(event);
      }}
      style={[style, pressed, disabled ? { opacity: 0.4 } : null]}>
      {children}
    </AnimatedPressable>
  );
}
