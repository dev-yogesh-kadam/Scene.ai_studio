import { LinearGradient } from 'expo-linear-gradient';
import { StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native';

import { Icon } from './Icon';
import { Tap } from './Tap';
import { Thumb } from './Thumb';
import { timeAgo } from '@scene/shared/format';
import { colors, fonts, gradient, radius, spacing } from '@/theme';
import type { ProjectRow } from '@scene/shared/types/api';

/** A project as a poster: its newest work as the cover, the name over a soft shade, and what's inside. */
export function ProjectCard({ project, onPress, style, compact }: { project: ProjectRow; onPress: () => void; style?: StyleProp<ViewStyle>; compact?: boolean }) {
  const parts = [
    project.modules ? `${project.modules + 1} modules` : null,
    `${project.items} ${project.items === 1 ? 'item' : 'items'}`,
    project.updated ? timeAgo(project.updated) : null,
  ].filter(Boolean);
  return (
    <Tap
      onPress={onPress}
      scaleTo={0.97}
      style={[styles.card, compact && styles.compact, style]}
      accessibilityLabel={[project.name, project.owner_name ? `shared by ${project.owner_name}` : null, ...parts].filter(Boolean).join(', ')}>
      {project.cover_id ? (
        <Thumb id={project.cover_id} kind={project.cover_kind ?? 'image'} style={StyleSheet.absoluteFill} iconSize={40} />
      ) : (
        <LinearGradient colors={[gradient[0] + '55', gradient[1] + '33']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={[StyleSheet.absoluteFill, styles.empty]}>
          <Icon name="folder-open" size={40} color={colors.textSecondary} />
        </LinearGradient>
      )}
      <LinearGradient colors={['transparent', 'rgba(0,0,0,0.85)']} style={styles.shade} />
      {project.owner_name ? (
        <View style={styles.shared}>
          <Icon name="people" size={12} color="#fff" />
          <Text style={styles.sharedText}>{project.owner_name}</Text>
        </View>
      ) : null}
      <View style={styles.caption}>
        <Text style={compact ? styles.nameSmall : styles.name} numberOfLines={1}>
          {project.name}
        </Text>
        <Text style={styles.meta} numberOfLines={1}>
          {parts.join('  ·  ')}
        </Text>
      </View>
    </Tap>
  );
}

const styles = StyleSheet.create({
  card: { aspectRatio: 16 / 10, borderRadius: radius.lg, overflow: 'hidden', backgroundColor: colors.surface, justifyContent: 'flex-end' },
  compact: { width: 260 },
  empty: { alignItems: 'center', justifyContent: 'center' },
  shade: { position: 'absolute', left: 0, right: 0, bottom: 0, height: '65%' },
  shared: {
    position: 'absolute',
    top: spacing.md,
    left: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: 'rgba(0,0,0,0.5)',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: radius.pill,
  },
  sharedText: { ...fonts.caption, color: '#fff' },
  caption: { padding: spacing.lg, gap: 2 },
  name: { ...fonts.title3, color: '#fff' },
  nameSmall: { ...fonts.headline, color: '#fff' },
  meta: { ...fonts.footnote, color: 'rgba(255,255,255,0.75)' },
});
