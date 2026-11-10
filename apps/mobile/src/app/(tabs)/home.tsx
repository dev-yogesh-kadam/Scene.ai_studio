import { useQuery, useQueryClient } from '@tanstack/react-query';
import { LinearGradient } from 'expo-linear-gradient';
import { router } from 'expo-router';
import { RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';

import { listLibrary } from '@scene/shared/api/library';
import { listProjects } from '@scene/shared/api/projects';
import { listJobs } from '@scene/shared/api/runs';
import { credits as creditsOf, waitingPlans } from '@scene/shared/api/studio';
import { Banner } from '@/components/Banner';
import { Icon, type IconName } from '@/components/Icon';
import { ItemTile } from '@/components/ItemTile';
import { ProgressBar } from '@/components/ProgressBar';
import { ProjectCard } from '@/components/ProjectCard';
import { Section } from '@/components/Section';
import { Skeleton } from '@/components/Skeleton';
import { Tap } from '@/components/Tap';
import { LargeTitle, TitledScreen, useBarInset, useScrollY } from '@/components/TitledScreen';
import { useColumns } from '@/hooks/useColumns';
import { useLive } from '@/hooks/useLive';
import { useScreenFocused } from '@/hooks/useScreenFocused';
import { useSession } from '@/hooks/useSession';
import { initials } from '@scene/shared/format';
import { isActive, pollEvery, progress, statusLine } from '@/lib/jobs';
import { colors, fonts, gradient, kindColors, radius, spacing } from '@/theme';
import type { Kind, LibraryItem } from '@scene/shared/types/api';

function greeting() {
  const hour = new Date().getHours();
  return hour < 5 ? 'Good Night' : hour < 12 ? 'Good Morning' : hour < 17 ? 'Good Afternoon' : 'Good Evening';
}

const QUICK: { kind: Kind; label: string; icon: IconName }[] = [
  { kind: 'video', label: 'Video', icon: 'film' },
  { kind: 'image', label: 'Image', icon: 'image' },
  { kind: 'audio', label: 'Music', icon: 'musical-notes' },
];

export default function HomeScreen() {
  const { user } = useSession();
  const focused = useScreenFocused();
  const live = useLive();
  const { columns, cell } = useColumns(2);
  const queryClient = useQueryClient();
  const { scrollY, onScroll } = useScrollY();
  const barInset = useBarInset();

  const projects = useQuery({ queryKey: ['projects'], queryFn: listProjects });
  const recent = useQuery({ queryKey: ['library', { home: true }], queryFn: () => listLibrary({ limit: 12 }) });
  const credits = useQuery({ queryKey: ['credits'], queryFn: creditsOf });
  const waiting = useQuery({ queryKey: ['waiting'], queryFn: waitingPlans, refetchInterval: focused ? 30_000 : false });
  const jobs = useQuery({
    queryKey: ['jobs'],
    queryFn: listJobs,
    refetchInterval: (query) => (focused ? pollEvery(live, !!query.state.data?.jobs.some(isActive)) : false),
  });

  const active = (jobs.data?.jobs ?? []).filter(isActive);
  const running = active.find((j) => j.status === 'running');
  const latest = (projects.data?.projects ?? [])
    .filter((p) => !p.parent_id)
    .sort((a, b) => (b.updated ?? b.created) - (a.updated ?? a.created))
    .slice(0, 6);
  const items = (recent.data?.items ?? []).slice(0, columns * 3);
  const firstName = user?.name.split(/\s+/)[0] ?? '';
  const balance = credits.data?.balance ?? user?.credits;

  const open = (item: LibraryItem) => {
    queryClient.setQueryData(['item', item.id], item);
    router.push({ pathname: '/watch/[id]', params: { id: String(item.id) } });
  };

  return (
    <TitledScreen
      title="Home"
      scrollY={scrollY}
      actions={
        <Tap
          onPress={() => router.push('/account')}
          haptic="light"
          scaleTo={0.9}
          // the name holds the initials the button shows, so "tap EU" works by voice too (WCAG 2.5.3)
          accessibilityLabel={`Account, ${initials(user?.name ?? '') || '?'}`}
        >
          <LinearGradient colors={gradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.avatar}>
            <Text style={styles.avatarText}>{initials(user?.name ?? '') || '?'}</Text>
          </LinearGradient>
        </Tap>
      }
    >
      <Animated.ScrollView
        onScroll={onScroll}
        scrollEventThrottle={16}
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={projects.isRefetching}
            onRefresh={() => {
              void projects.refetch();
              void recent.refetch();
              void jobs.refetch();
              void credits.refetch();
              void waiting.refetch();
            }}
            progressViewOffset={barInset}
            tintColor={colors.textSecondary}
            colors={[colors.accent]}
            progressBackgroundColor={colors.surface}
          />
        }
      >
        <LargeTitle
          title={firstName ? `${greeting()}, ${firstName}` : greeting()}
          subtitle={balance != null ? `${balance.toLocaleString()} credits` : undefined}
          scrollY={scrollY}
        />

        <View style={styles.sections}>
          {projects.error ? (
            <View style={styles.pad}>
              <Banner tone="danger" text={projects.error.message} />
            </View>
          ) : null}

          {active.length ? (
            <Animated.View entering={FadeIn.duration(200)} style={styles.pad}>
              <Tap
                onPress={() => router.push('/activity')}
                scaleTo={0.98}
                style={styles.live}
                accessibilityLabel={running ? `Rendering ${running.name}. ${statusLine(running)}` : 'Jobs in line'}
                accessibilityHint="Opens Activity."
              >
                <View style={styles.liveTop}>
                  <View style={styles.liveDot} />
                  <Text style={styles.liveLabel}>
                    {[
                      running && `${active.filter((j) => j.status === 'running').length} rendering`,
                      active.some((j) => j.status === 'queued') &&
                        `${active.filter((j) => j.status === 'queued').length} in line`,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </Text>
                  <Icon name="chevron-forward" size={16} color={colors.textSecondary} />
                </View>
                {running ? (
                  <>
                    <Text style={styles.liveName} numberOfLines={1}>
                      {running.name}
                    </Text>
                    <Text style={styles.liveStatus} numberOfLines={1}>
                      {statusLine(running)}
                    </Text>
                    <ProgressBar value={progress(running)} />
                  </>
                ) : (
                  <Text style={styles.liveStatus}>{statusLine(active[0])}</Text>
                )}
              </Tap>
            </Animated.View>
          ) : null}

          {waiting.data?.plans.length ? (
            <Section title="Waiting for You">
              <View style={styles.waitingList}>
                {waiting.data.plans.slice(0, 3).map((plan) => (
                  <Tap
                    key={`${plan.project_id}-${plan.tab}`}
                    onPress={() =>
                      router.push({ pathname: '/chat/[id]', params: { id: String(plan.project_id), tab: plan.tab } })
                    }
                    scaleTo={0.98}
                    style={styles.waiting}
                  >
                    <View style={styles.waitingIcon}>
                      <Icon name="hand-left" size={18} color={colors.warning} />
                    </View>
                    <View style={{ flex: 1, gap: 2 }}>
                      <Text style={styles.waitingTitle} numberOfLines={1}>
                        {plan.instruction || 'A plan'}
                      </Text>
                      <Text style={styles.waitingMeta} numberOfLines={1}>
                        {plan.steps} {plan.steps === 1 ? 'step' : 'steps'} · {plan.total.toLocaleString()} cr ·{' '}
                        {plan.project} › {plan.module}
                      </Text>
                    </View>
                    <Text style={styles.waitingAction}>Review</Text>
                  </Tap>
                ))}
              </View>
            </Section>
          ) : null}

          <Animated.View entering={FadeIn.duration(200)} style={styles.pad}>
            <View style={styles.create}>
              <LinearGradient
                colors={[colors.heroFrom, colors.heroTo]}
                start={{ x: 0, y: 0 }}
                end={{ x: 1, y: 1 }}
                style={StyleSheet.absoluteFill}
              />
              <Text style={styles.createTitle}>What will you make today?</Text>
              <View style={styles.quick}>
                {QUICK.map((q) => (
                  <Tap
                    key={q.kind}
                    onPress={() => router.navigate({ pathname: '/create', params: { kind: q.kind } })}
                    haptic="light"
                    scaleTo={0.94}
                    style={styles.quickButton}
                    accessibilityLabel={`Make ${q.kind === 'audio' ? 'music' : q.kind === 'image' ? 'an image' : `a ${q.label.toLowerCase()}`}`}
                  >
                    <Icon name={q.icon} size={22} color={kindColors[q.kind]} />
                    <Text style={styles.quickLabel}>{q.label}</Text>
                  </Tap>
                ))}
              </View>
            </View>
          </Animated.View>

          <Section title="Projects" onSeeAll={() => router.navigate('/projects')} padded={false}>
            {projects.isPending ? (
              <View style={[styles.pad, { flexDirection: 'row', gap: spacing.md }]}>
                <Skeleton style={{ width: 260, aspectRatio: 16 / 10, borderRadius: radius.lg }} />
                <Skeleton style={{ width: 260, aspectRatio: 16 / 10, borderRadius: radius.lg }} />
              </View>
            ) : latest.length ? (
              <ScrollView
                horizontal
                showsHorizontalScrollIndicator={false}
                contentContainerStyle={styles.row}
                decelerationRate="fast"
                snapToInterval={260 + spacing.md}
              >
                {latest.map((project) => (
                  <ProjectCard
                    key={project.id}
                    compact
                    project={project}
                    onPress={() => router.push({ pathname: '/project/[id]', params: { id: String(project.id) } })}
                  />
                ))}
              </ScrollView>
            ) : (
              <Text style={[styles.emptyText, styles.pad]}>Projects you make in the studio show up here.</Text>
            )}
          </Section>

          <Section title="Recent" onSeeAll={() => router.navigate('/library')}>
            {recent.isPending ? (
              <View style={styles.grid}>
                {Array.from({ length: columns * 2 }, (_, i) => (
                  <Skeleton key={i} style={{ width: cell, aspectRatio: 1, borderRadius: radius.md }} />
                ))}
              </View>
            ) : items.length ? (
              <View style={styles.grid}>
                {items.map((item) => (
                  <View key={item.id} style={{ width: cell }}>
                    <ItemTile item={item} onPress={() => open(item)} onLongPress={() => open(item)} />
                  </View>
                ))}
              </View>
            ) : (
              <Text style={styles.emptyText}>Nothing made yet. Tap Video, Image or Music above to start.</Text>
            )}
          </Section>
        </View>
      </Animated.ScrollView>
    </TitledScreen>
  );
}

const styles = StyleSheet.create({
  content: { paddingBottom: spacing.xxl },
  sections: { gap: spacing.xxl },
  pad: { paddingHorizontal: spacing.lg },
  avatar: { width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center' },
  avatarText: { ...fonts.footnoteStrong, color: colors.onBrand },
  live: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, gap: 6 },
  liveTop: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  liveDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.accent },
  liveLabel: { ...fonts.footnoteStrong, color: colors.accent, flex: 1, textTransform: 'uppercase', letterSpacing: 0.4 },
  liveName: { ...fonts.headline, color: colors.text },
  liveStatus: { ...fonts.subhead, color: colors.textSecondary, marginBottom: 4 },
  create: { borderRadius: radius.lg, padding: spacing.xl, gap: spacing.lg, overflow: 'hidden' },
  createTitle: { ...fonts.title3, color: colors.text },
  quick: { flexDirection: 'row', gap: spacing.md },
  quickButton: {
    flex: 1,
    alignItems: 'center',
    gap: 6,
    paddingVertical: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.heroButton,
  },
  quickLabel: { ...fonts.footnoteStrong, color: colors.text },
  row: { paddingHorizontal: spacing.lg, gap: spacing.md },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md, rowGap: spacing.xl },
  cell: { width: '47.5%' },
  emptyText: { ...fonts.subhead, color: colors.textSecondary },
  waitingList: { gap: spacing.sm },
  waiting: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.md,
    paddingRight: spacing.lg,
  },
  waitingIcon: {
    width: 40,
    height: 40,
    borderRadius: 12,
    backgroundColor: colors.warningSoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  waitingTitle: { ...fonts.subheadStrong, color: colors.text },
  waitingMeta: { ...fonts.caption, color: colors.textSecondary },
  waitingAction: { ...fonts.subheadStrong, color: colors.accent },
});
