import { StyleSheet, Text, View } from 'react-native';

import { Button } from './Button';
import { Icon } from './Icon';
import { Sheet } from './Sheet';
import type { Release } from '@/lib/whatsNew';
import { colors, fonts, radius, spacing } from '@/theme';

/** A version's news as a sheet: a symbol, a title and a line per point, then Continue. */
export function WhatsNew({ release, onClose }: { release: Release | null; onClose: () => void }) {
  return (
    <Sheet open={!!release} onClose={onClose} title={release ? `What's New in ${release.version}` : undefined}>
      {release ? (
        <View style={{ gap: spacing.lg }}>
          {release.points.map((point) => (
            <View key={point.title} style={styles.point}>
              <View style={styles.icon}>
                <Icon name={point.icon} size={22} color={colors.accent} />
              </View>
              <View style={{ flex: 1, gap: 2 }}>
                <Text style={styles.title}>{point.title}</Text>
                <Text style={styles.text}>{point.text}</Text>
              </View>
            </View>
          ))}
          <Button label="Continue" onPress={onClose} />
        </View>
      ) : null}
    </Sheet>
  );
}

const styles = StyleSheet.create({
  point: { flexDirection: 'row', gap: spacing.md, alignItems: 'flex-start' },
  icon: { width: 44, height: 44, borderRadius: radius.md, backgroundColor: colors.accentSoft, alignItems: 'center', justifyContent: 'center' },
  title: { ...fonts.headline, color: colors.text },
  text: { ...fonts.subhead, color: colors.textSecondary },
});
