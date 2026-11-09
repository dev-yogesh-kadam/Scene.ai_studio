import { useQuery } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useMemo, useState } from 'react';
import { RefreshControl, StyleSheet, Text, TextInput, View } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';

import { listSkills } from '@/api/skills';
import { Banner } from '@/components/Banner';
import { EmptyState } from '@/components/EmptyState';
import { Icon } from '@/components/Icon';
import { Segmented } from '@/components/Segmented';
import { Skeleton } from '@/components/Skeleton';
import { Tap } from '@/components/Tap';
import { LargeTitle, TitledScreen, useBarInset, useScrollY } from '@/components/TitledScreen';
import { skillLook } from '@/lib/skills';
import { colors, fonts, radius, spacing } from '@/theme';
import type { Skill } from '@/types/api';

type Filter = 'all' | 'craft' | 'make';

export default function SkillsScreen() {
  const { scrollY, onScroll } = useScrollY();
  const barInset = useBarInset();
  const [filter, setFilter] = useState<Filter>('all');
  const [q, setQ] = useState('');
  const skills = useQuery({ queryKey: ['skills'], queryFn: listSkills, staleTime: 10 * 60_000 });

  const shown = useMemo(() => {
    const words = q.trim().toLowerCase();
    return (skills.data?.skills ?? [])
      .filter((s) => (filter === 'all' ? true : filter === 'craft' ? s.craft : !s.craft))
      .filter((s) => !words || `${s.title} ${s.desc} ${s.id}`.toLowerCase().includes(words))
      .sort((a, b) => Number(b.craft) - Number(a.craft) || a.title.localeCompare(b.title));
  }, [skills.data, filter, q]);

  return (
    <TitledScreen title="Skills" scrollY={scrollY}>
      <Animated.FlatList
        data={shown}
        keyExtractor={(s) => s.id}
        onScroll={onScroll}
        scrollEventThrottle={16}
        keyboardDismissMode="on-drag"
        contentContainerStyle={styles.list}
        ListHeaderComponent={
          <View style={styles.header}>
            <LargeTitle title="Skills" subtitle="What the agent knows how to do" scrollY={scrollY} />
            <View style={styles.pad}>
              <View style={styles.search}>
                <Icon name="search" size={18} color={colors.textSecondary} />
                <TextInput
                  style={styles.searchInput}
                  placeholder="Search skills"
                  placeholderTextColor={colors.textSecondary}
                  value={q}
                  onChangeText={setQ}
                  returnKeyType="search"
                />
              </View>
              <Segmented
                options={[
                  { value: 'all', label: 'All' },
                  { value: 'craft', label: 'Craft' },
                  { value: 'make', label: 'Recipes' },
                ]}
                value={filter}
                onChange={setFilter}
              />
              {skills.error ? <Banner tone="danger" text={skills.error.message} /> : null}
            </View>
          </View>
        }
        renderItem={({ item, index }) => (
          <Animated.View entering={FadeIn.duration(200)} style={styles.item}>
            <SkillRow skill={item} />
          </Animated.View>
        )}
        ListEmptyComponent={
          skills.isPending ? (
            <View style={[styles.pad, { gap: spacing.md }]}>
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} style={{ height: 84, borderRadius: radius.lg }} />
              ))}
            </View>
          ) : (
            <EmptyState icon="bulb-outline" title="No Skills Found" />
          )
        }
        refreshControl={
          <RefreshControl
            refreshing={skills.isRefetching}
            onRefresh={() => void skills.refetch()}
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

function SkillRow({ skill }: { skill: Skill }) {
  const look = skillLook(skill);
  return (
    <Tap
      onPress={() => router.push({ pathname: '/skill/[id]', params: { id: skill.id } })}
      scaleTo={0.98}
      style={styles.row}
      accessibilityLabel={`${skill.title}${skill.craft ? ', craft skill' : ''}. ${skill.desc}`}>
      <View style={[styles.icon, { backgroundColor: look.color }]}>
        <Icon name={look.icon} size={22} color="#fff" />
      </View>
      <View style={styles.text}>
        <View style={styles.titleRow}>
          <Text style={styles.title} numberOfLines={1}>
            {skill.title}
          </Text>
          {skill.craft ? <Text style={styles.tag}>CRAFT</Text> : null}
        </View>
        <Text style={styles.desc} numberOfLines={2}>
          {skill.desc}
        </Text>
      </View>
      <Icon name="chevron-forward" size={18} color={colors.textMuted} />
    </Tap>
  );
}

const styles = StyleSheet.create({
  list: { paddingBottom: spacing.xxl },
  header: { paddingBottom: spacing.lg },
  pad: { paddingHorizontal: spacing.lg, gap: spacing.md },
  search: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, height: 38, backgroundColor: colors.fill, borderRadius: radius.sm + 2 },
  searchInput: { flex: 1, ...fonts.body, color: colors.text, paddingVertical: 0 },
  item: { paddingHorizontal: spacing.lg, marginBottom: spacing.sm },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.md, paddingRight: spacing.lg },
  icon: { width: 44, height: 44, borderRadius: 11, alignItems: 'center', justifyContent: 'center' },
  text: { flex: 1, gap: 2 },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  title: { ...fonts.headline, color: colors.text, flexShrink: 1 },
  tag: { ...fonts.caption2, color: colors.accent, letterSpacing: 0.5 },
  desc: { ...fonts.footnote, color: colors.textSecondary },
});
