import { StyleSheet, Text, View } from 'react-native';
import Animated, { FadeIn, FadeOutUp } from 'react-native-reanimated';

import { Icon, type IconName } from './Icon';
import { colors, fonts, radius, spacing } from '@/theme';

const tones = {
  info: { color: colors.accent, icon: 'information-circle' as IconName },
  warning: { color: colors.warning, icon: 'warning' as IconName },
  danger: { color: colors.danger, icon: 'alert-circle' as IconName },
  success: { color: colors.success, icon: 'checkmark-circle' as IconName },
};

export type Tone = keyof typeof tones;

/** A notice above a list: the jobs are paused, an admin's message, an error. */
export function Banner({ tone = 'info', text, icon }: { tone?: Tone; text: string; icon?: IconName }) {
  const look = tones[tone] ?? tones.info;
  return (
    <Animated.View entering={FadeIn.duration(200)} exiting={FadeOutUp} style={styles.banner} accessibilityLiveRegion="polite" accessible>
      <View style={[styles.iconBox, { backgroundColor: look.color + '26' }]}>
        <Icon name={icon ?? look.icon} size={18} color={look.color} />
      </View>
      <Text style={styles.text}>{text}</Text>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
  },
  iconBox: { width: 32, height: 32, borderRadius: 9, alignItems: 'center', justifyContent: 'center' },
  text: { ...fonts.footnote, color: colors.text, flex: 1 },
});
