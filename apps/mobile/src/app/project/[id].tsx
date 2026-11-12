import { useQuery } from '@tanstack/react-query';
import { LinearGradient } from 'expo-linear-gradient';
import { router, useLocalSearchParams } from 'expo-router';
import { RefreshControl, StyleSheet, Text, View } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';

import { getProject } from '@scene/shared/api/projects';
import { Banner } from '@/components/Banner';
import { EmptyState } from '@/components/EmptyState';
import { Icon } from '@/components/Icon';
import { Skeleton } from '@/components/Skeleton';
import { Tap } from '@/components/Tap';
import { Thumb } from '@/components/Thumb';
import { LargeTitle, TitledScreen, useBarInset, useScrollY } from '@/components/TitledScreen';
import { initials, timeAgo } from '@scene/shared/format';
import { colors, fonts, gradient, radius, spacing } from '@/theme';
import type { ModuleRow } from '@scene/shared/types/api';

const roleWords: Record<string, string> = { owner: 'Owner', manager: 'Manager', creator: 'Creator', viewer: 'Viewer' };

export default function ProjectScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const projectId = Number(id);
  const { scrollY, onScroll } = useScrollY();
  const barInset = useBarInset();
  const detail = useQuery({ queryKey: ['project', projectId], queryFn: () => getProject(projectId) });

  const project = detail.data?.project;
  const modules = detail.data?.modules ?? [];
  const members = project?.members ?? [];

  return (
    <TitledScreen title={project?.name ?? 'Project'} back scrollY={scrollY}>
      <Animated.FlatList
        data={modules}
        keyExtractor={(m) => String(m.id)}
        onScroll={onScroll}
        scrollEventThrottle={16}
        contentContainerStyle={styles.list}
        ListHeaderComponent={
          <View style={styles.header}>
            <LargeTitle title={project?.name ?? ' '} subtitle={project ? `${roleWords[project.role] ?? project.role} · made ${timeAgo(project.created)}` : undefined} scrollY={scrollY} />
            {detail.error ? (
              <View style={styles.pad}>
                <Banner tone="danger" text={detail.error.message} />
              </View>
            ) : null}
            {project ? (
              <Animated.View entering={FadeIn.duration(200)} style={[styles.pad, styles.stats]}>
                <Stat value={String(modules.length)} label={modules.length === 1 ? 'Module' : 'Modules'} />
                <Stat value={project.items.toLocaleString()} label={project.items === 1 ? 'Item' : 'Items'} />
                <Stat value={project.updated ? timeAgo(project.updated) : '—'} label="Last Change" />
              </Animated.View>
            ) : null}
            {members.length > 1 ? (
              <View style={[styles.pad, styles.members]}>
                <View style={styles.faces}>
                  {members.slice(0, 5).map((m, i) => (
                    <LinearGradient key={m.user_id} colors={gradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={[styles.face, { marginLeft: i ? -8 : 0 }]}>
                      <Text style={styles.faceText}>{initials(m.name)}</Text>
                    </LinearGradient>
                  ))}
                </View>
                <Text style={styles.membersText} numberOfLines={1}>
                  {members.map((m) => m.name.split(' ')[0]).join(', ')}
                </Text>
              </View>
            ) : null}
            <Text style={styles.sectionTitle}>Modules</Text>
          </View>
        }
        renderItem={({ item, index }) => (
          <Animated.View entering={FadeIn.duration(200)} style={styles.item}>
            <ModuleCard module={item} onPress={() => router.push({ pathname: '/canvas/[id]', params: { id: String(item.id) } })} />
          </Animated.View>
        )}
        ListEmptyComponent={
          detail.isPending ? (
            <View style={[styles.pad, { gap: spacing.md }]}>
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} style={{ height: 92, borderRadius: radius.lg }} />
              ))}
            </View>
          ) : (
            <EmptyState icon="grid-outline" title="No Modules" />
          )
        }
        refreshControl={
          <RefreshControl
            refreshing={detail.isRefetching}
            onRefresh={() => void detail.refetch()}
            progressViewOffset={barInset}
            tintColor={colors.textSecondary}
            colors={[colors.accent]}
            progressBackgroundColor={colors.surface}
          />
        }
      />
    </TitledScreen>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue} numberOfLines={1}>
        {value}
      </Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

function ModuleCard({ module, onPress }: { module: ModuleRow; onPress: () => void }) {
  return (
    <Tap
      onPress={onPress}
      scaleTo={0.98}
      style={styles.card}
      accessibilityLabel={`${module.name}${module.main ? ', main canvas' : ''}, ${module.items} ${module.items === 1 ? 'item' : 'items'}`}>
      {module.cover_id ? (
        <Thumb id={module.cover_id} kind={module.cover_kind ?? 'image'} style={styles.cover} iconSize={26} />
      ) : (
        <View style={[styles.cover, styles.coverEmpty]}>
          <Icon name={module.main ? 'easel-outline' : 'albums-outline'} size={26} color={colors.textMuted} />
        </View>
      )}
      <View style={styles.cardText}>
        <View style={styles.cardTitleRow}>
          <Text style={styles.cardTitle} numberOfLines={1}>
            {module.name}
          </Text>
          {module.main ? (
            <View style={styles.badge}>
              <Text style={styles.badgeText}>Main</Text>
            </View>
          ) : null}
        </View>
        <Text style={styles.cardMeta} numberOfLines={1}>
          {module.items} {module.items === 1 ? 'item' : 'items'}
          {module.updated ? `  ·  ${timeAgo(module.updated)}` : ''}
        </Text>
      </View>
      <Icon name="chevron-forward" size={18} color={colors.textMuted} />
    </Tap>
  );
}

const styles = StyleSheet.create({
  list: { paddingBottom: spacing.xxl },
  header: { gap: spacing.lg, paddingBottom: spacing.md },
  pad: { paddingHorizontal: spacing.lg },
  stats: { flexDirection: 'row', gap: spacing.sm },
  stat: { flex: 1, backgroundColor: colors.surface, borderRadius: radius.md, paddingVertical: spacing.md, paddingHorizontal: spacing.sm, alignItems: 'center' },
  statValue: { ...fonts.title3, color: colors.text },
  statLabel: { ...fonts.caption, color: colors.textSecondary },
  members: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  faces: { flexDirection: 'row' },
  face: { width: 30, height: 30, borderRadius: 15, alignItems: 'center', justifyContent: 'center', borderWidth: 2, borderColor: colors.background },
  faceText: { ...fonts.caption2, color: colors.onBrand },
  membersText: { ...fonts.subhead, color: colors.textSecondary, flex: 1 },
  sectionTitle: { ...fonts.title2, color: colors.text, paddingHorizontal: spacing.lg, marginTop: spacing.sm },
  item: { paddingHorizontal: spacing.lg, marginBottom: spacing.md },
  card: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.sm, paddingRight: spacing.lg },
  cover: { width: 112, height: 72, borderRadius: radius.md },
  coverEmpty: { backgroundColor: colors.surfaceRaised, alignItems: 'center', justifyContent: 'center' },
  cardText: { flex: 1, gap: 3 },
  cardTitleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  cardTitle: { ...fonts.headline, color: colors.text, flexShrink: 1 },
  badge: { backgroundColor: colors.accentSoft, paddingHorizontal: 7, paddingVertical: 2, borderRadius: radius.pill },
  badgeText: { ...fonts.caption2, color: colors.accent },
  cardMeta: { ...fonts.footnote, color: colors.textSecondary },
});
