import { StyleSheet, Text, View } from 'react-native';

import { Icon } from './Icon';
import { Tap } from './Tap';
import { Thumb } from './Thumb';
import { clipLength, timeAgo } from '@scene/shared/format';
import { colors, fonts, radius, spacing } from '@/theme';
import type { LibraryItem } from '@scene/shared/types/api';

type Props = {
  item: LibraryItem;
  onPress: () => void;
  onLongPress: () => void;
};

const kindWords: Record<string, string> = { video: 'Video', image: 'Image', audio: 'Audio', text: 'Text' };

/** A tile in the library grid, as Apple TV and Music lay out albums: the artwork, then a title and a quiet line. */
export function ItemTile({ item, onPress, onLongPress }: Props) {
  const length = item.kind === 'video' || item.kind === 'audio' ? clipLength(item.seconds) : null;
  return (
    <Tap
      onPress={onPress}
      onLongPress={onLongPress}
      delayLongPress={320}
      scaleTo={0.96}
      style={styles.tile}
      accessibilityLabel={[item.name, kindWords[item.kind] ?? item.kind, length, item.rating > 0 ? 'best take' : null, timeAgo(item.created)].filter(Boolean).join(', ')}
      accessibilityHint="Opens it. Touch and hold to mark it as a best take.">
      <View style={styles.art}>
        <Thumb id={item.id} kind={item.kind} style={StyleSheet.absoluteFill} />
        {length ? (
          <View style={[styles.badge, styles.length]}>
            <Text style={styles.badgeText}>{length}</Text>
          </View>
        ) : null}
        {item.rating > 0 ? (
          <View style={[styles.badge, styles.star]}>
            <Icon name="star" size={12} color={colors.star} />
          </View>
        ) : null}
      </View>
      <Text style={styles.name} numberOfLines={1}>
        {item.name}
      </Text>
      <Text style={styles.meta} numberOfLines={1}>
        {kindWords[item.kind] ?? item.kind}  ·  {timeAgo(item.created)}
      </Text>
    </Tap>
  );
}

const styles = StyleSheet.create({
  tile: { flex: 1 },
  art: { aspectRatio: 1, borderRadius: radius.md, overflow: 'hidden', backgroundColor: colors.surface },
  badge: { position: 'absolute', backgroundColor: 'rgba(0,0,0,0.5)', borderRadius: radius.pill, paddingHorizontal: 7, paddingVertical: 3 },
  length: { right: spacing.sm, bottom: spacing.sm },
  star: { left: spacing.sm, bottom: spacing.sm, paddingHorizontal: 5 },
  badgeText: { ...fonts.caption2, color: '#fff' },
  name: { ...fonts.subheadStrong, color: colors.text, marginTop: spacing.sm },
  meta: { ...fonts.footnote, color: colors.textSecondary },
});
