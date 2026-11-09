import { useQuery } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useMemo, useState } from 'react';
import { RefreshControl, StyleSheet, TextInput, View } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';

import { listProjects } from '@/api/projects';
import { Banner } from '@/components/Banner';
import { EmptyState } from '@/components/EmptyState';
import { Icon } from '@/components/Icon';
import { ProjectCard } from '@/components/ProjectCard';
import { Segmented } from '@/components/Segmented';
import { Skeleton } from '@/components/Skeleton';
import { Tap } from '@/components/Tap';
import { LargeTitle, TitledScreen, useBarInset, useScrollY } from '@/components/TitledScreen';
import { useColumns } from '@/hooks/useColumns';
import { colors, fonts, radius, spacing } from '@/theme';

type Order = 'recent' | 'name';

export default function ProjectsScreen() {
  const { scrollY, onScroll } = useScrollY();
  const barInset = useBarInset();
  const [order, setOrder] = useState<Order>('recent');
  const { columns, cell } = useColumns(1, spacing.lg);
  const [q, setQ] = useState('');
  const projects = useQuery({ queryKey: ['projects'], queryFn: listProjects });

  const shown = useMemo(() => {
    const all = projects.data?.projects ?? [];
    const words = q.trim().toLowerCase();
    // A module found by name brings its project, so a search for "scene 3" still lands somewhere.
    const matching = words
      ? new Set(all.filter((p) => p.name.toLowerCase().includes(words)).map((p) => p.parent_id ?? p.id))
      : null;
    const tops = all.filter((p) => !p.parent_id && (!matching || matching.has(p.id)));
    return order === 'name'
      ? tops.sort((a, b) => a.name.localeCompare(b.name))
      : tops.sort((a, b) => (b.updated ?? b.created) - (a.updated ?? a.created));
  }, [projects.data, q, order]);

  const count = projects.data ? projects.data.projects.filter((p) => !p.parent_id).length : 0;

  return (
    <TitledScreen title="Projects" scrollY={scrollY}>
      <Animated.FlatList
        data={shown}
        keyExtractor={(p) => String(p.id)}
        key={columns}
        numColumns={columns}
        columnWrapperStyle={columns > 1 ? { gap: spacing.lg, paddingHorizontal: spacing.lg } : undefined}
        onScroll={onScroll}
        scrollEventThrottle={16}
        keyboardDismissMode="on-drag"
        contentContainerStyle={styles.list}
        ListHeaderComponent={
          <View style={styles.header}>
            <LargeTitle title="Projects" subtitle={count ? `${count} ${count === 1 ? 'project' : 'projects'}` : undefined} scrollY={scrollY} />
            <View style={styles.pad}>
              <View style={styles.search}>
                <Icon name="search" size={18} color={colors.textSecondary} />
                <TextInput
                  style={styles.searchInput}
                  placeholder="Search projects and modules"
                  placeholderTextColor={colors.textSecondary}
                  value={q}
                  onChangeText={setQ}
                  returnKeyType="search"
                />
                {q ? (
                  <Tap onPress={() => setQ('')} hitSlop={10}>
                    <Icon name="close-circle" size={18} color={colors.textSecondary} />
                  </Tap>
                ) : null}
              </View>
              <Segmented
                options={[
                  { value: 'recent', label: 'Recent' },
                  { value: 'name', label: 'A–Z' },
                ]}
                value={order}
                onChange={setOrder}
              />
              {projects.error ? <Banner tone="danger" text={projects.error.message} /> : null}
            </View>
          </View>
        }
        renderItem={({ item, index }) => (
          <Animated.View
            entering={FadeIn.duration(200)}
            style={columns > 1 ? { width: cell, marginBottom: spacing.lg } : styles.item}>
            <ProjectCard project={item} onPress={() => router.push({ pathname: '/project/[id]', params: { id: String(item.id) } })} />
          </Animated.View>
        )}
        ListEmptyComponent={
          projects.isPending ? (
            <View style={[styles.pad, { gap: spacing.lg }]}>
              <Skeleton style={styles.skeleton} />
              <Skeleton style={styles.skeleton} />
            </View>
          ) : q ? (
            <EmptyState icon="search" title="No Results" text={`Nothing called “${q}”.`} />
          ) : (
            <EmptyState icon="folder-open-outline" title="No Projects Yet" text="Make a project in the studio and it shows up here with its modules." />
          )
        }
        refreshControl={
          <RefreshControl
            refreshing={projects.isRefetching}
            onRefresh={() => void projects.refetch()}
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

const styles = StyleSheet.create({
  list: { paddingBottom: spacing.xxl },
  header: { paddingBottom: spacing.lg },
  pad: { paddingHorizontal: spacing.lg, gap: spacing.md },
  search: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 10,
    height: 38,
    backgroundColor: colors.fill,
    borderRadius: radius.sm + 2,
  },
  searchInput: { flex: 1, ...fonts.body, color: colors.text, paddingVertical: 0 },
  item: { paddingHorizontal: spacing.lg, marginBottom: spacing.lg },
  skeleton: { aspectRatio: 16 / 10, borderRadius: radius.lg },
});
