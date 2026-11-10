import type { ReactNode } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Icon } from './Icon';
import { Tap } from './Tap';
import { colors, fonts, spacing } from '@/theme';

/** A titled part of a scrolling page, as on the App Store's Today and Apple Music: a bold title, maybe "See All". */
export function Section({ title, onSeeAll, children, padded = true }: { title: string; onSeeAll?: () => void; children: ReactNode; padded?: boolean }) {
  return (
    <View style={styles.section}>
      <View style={styles.header}>
        <Text style={styles.title} accessibilityRole="header">
          {title}
        </Text>
        {onSeeAll ? (
          <Tap onPress={onSeeAll} hitSlop={10} scaleTo={0.94} style={styles.more}>
            <Text style={styles.moreText}>See All</Text>
            <Icon name="chevron-forward" size={15} color={colors.accent} />
          </Tap>
        ) : null}
      </View>
      <View style={padded ? styles.padded : null}>{children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: spacing.md },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: spacing.lg },
  title: { ...fonts.title2, color: colors.text },
  more: { flexDirection: 'row', alignItems: 'center', gap: 2 },
  moreText: { ...fonts.body, color: colors.accent },
  padded: { paddingHorizontal: spacing.lg },
});
