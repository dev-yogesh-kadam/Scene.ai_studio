import type { ReactNode } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';

import { Icon, type IconName } from './Icon';
import { colors, fonts, spacing } from '@/theme';

/** What a list shows when there's nothing in it: a big quiet symbol, a title, a line, maybe one button. */
export function EmptyState({ icon, title, text, children }: { icon: IconName; title: string; text?: string; children?: ReactNode }) {
  return (
    <Animated.View entering={FadeIn.duration(400)} style={styles.box}>
      <Icon name={icon} size={56} color={colors.textMuted} />
      <Text style={styles.title}>{title}</Text>
      {text ? <Text style={styles.text}>{text}</Text> : null}
      {children ? <View style={styles.actions}>{children}</View> : null}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  box: { alignItems: 'center', justifyContent: 'center', paddingVertical: 72, paddingHorizontal: spacing.xxl, gap: spacing.sm },
  title: { ...fonts.title3, color: colors.text, textAlign: 'center', marginTop: spacing.md },
  text: { ...fonts.subhead, color: colors.textSecondary, textAlign: 'center' },
  actions: { marginTop: spacing.xl, alignSelf: 'stretch', paddingHorizontal: spacing.xl },
});
