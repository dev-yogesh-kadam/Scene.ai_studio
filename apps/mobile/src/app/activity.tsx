import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as Haptics from '@/lib/haptics';
import { router } from 'expo-router';
import { useEffect, useMemo, useRef } from 'react';
import { RefreshControl, StyleSheet, Text, View } from 'react-native';
import Animated, { FadeIn, FadeOut, LinearTransition } from 'react-native-reanimated';

import { listJobs, removeJob, retryJob } from '@scene/shared/api/runs';
import { announcement } from '@scene/shared/api/studio';
import { Banner, type Tone } from '@/components/Banner';
import { Button, IconButton } from '@/components/Button';
import { EmptyState } from '@/components/EmptyState';
import { JobCard } from '@/components/JobCard';
import { JobSkeletons } from '@/components/Skeleton';
import { LargeTitle, TitledScreen, useBarInset, useScrollY } from '@/components/TitledScreen';
import { useToast } from '@/components/Toast';
import { useLive } from '@/hooks/useLive';
import { useScreenFocused } from '@/hooks/useScreenFocused';
import { isActive, pollEvery, sortJobs } from '@/lib/jobs';
import { colors, fonts, spacing } from '@/theme';
import type { Job } from '@scene/shared/types/api';
import { Alert } from '@/lib/dialog';

type Line = { type: 'section'; key: string; title: string } | { type: 'job'; key: string; job: Job };

export default function ActivityScreen() {
  const focused = useScreenFocused();
  const live = useLive();
  const queryClient = useQueryClient();
  const toast = useToast();
  const { scrollY, onScroll } = useScrollY();
  const barInset = useBarInset();

  const jobs = useQuery({
    queryKey: ['jobs'],
    queryFn: listJobs,
    // Only while the live line is down (it says every change): quick while something is rendering, slower when
    // everything has ended; never while the screen is hidden.
    refetchInterval: (query) => (focused ? pollEvery(live, !!query.state.data?.jobs.some(isActive)) : false),
  });
  const notice = useQuery({
    queryKey: ['announcement'],
    queryFn: announcement,
    refetchInterval: focused ? 60_000 : false,
  });

  // A tap felt when something finishes while you're watching.
  const seen = useRef(new Map<string, string>());
  useEffect(() => {
    let ready = false;
    let failed = false;
    for (const job of jobs.data?.jobs ?? []) {
      const before = seen.current.get(job.id);
      if (before && before !== job.status) {
        if (job.status === 'done') ready = true;
        if (job.status === 'failed') failed = true;
      }
      seen.current.set(job.id, job.status);
    }
    if (ready) {
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      void queryClient.invalidateQueries({ queryKey: ['library'] });
    } else if (failed) void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
  }, [jobs.data, queryClient]);

  const retry = useMutation({
    mutationFn: (job: Job) => retryJob(job.id),
    onSuccess: (answer) => {
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      toast(answer.credits ? `Queued again · ${answer.credits} credits` : 'Queued again', { icon: 'refresh-circle' });
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
      void queryClient.invalidateQueries({ queryKey: ['credits'] });
    },
    onError: (error) => Alert.alert("Couldn't run it again", error.message),
  });

  const remove = useMutation({
    mutationFn: (job: Job) => removeJob(job.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
      void queryClient.invalidateQueries({ queryKey: ['credits'] });
    },
    onError: (error) => Alert.alert("Couldn't do that", error.message),
  });

  function confirmRemove(job: Job) {
    if (!isActive(job)) return remove.mutate(job);
    void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    Alert.alert(
      job.status === 'running' ? 'Stop this render?' : 'Cancel this job?',
      job.status === 'running'
        ? 'It stops now and your credits come back.'
        : 'It leaves the line and your credits come back.',
      [
        { text: 'Keep It', style: 'cancel' },
        {
          text: job.status === 'running' ? 'Stop' : 'Cancel Job',
          style: 'destructive',
          onPress: () => remove.mutate(job),
        },
      ],
    );
  }

  const lines = useMemo<Line[]>(() => {
    const sorted = sortJobs(jobs.data?.jobs ?? []);
    const now = sorted.filter(isActive);
    const ended = sorted.filter((job) => !isActive(job));
    return [
      ...(now.length ? [{ type: 'section' as const, key: 's-now', title: 'In Progress' }] : []),
      ...now.map((job) => ({ type: 'job' as const, key: job.id, job })),
      ...(ended.length ? [{ type: 'section' as const, key: 's-ended', title: 'Recent' }] : []),
      ...ended.map((job) => ({ type: 'job' as const, key: job.id, job })),
    ];
  }, [jobs.data]);

  const running = jobs.data?.jobs.filter((j) => j.status === 'running').length ?? 0;
  const queued = jobs.data?.jobs.filter((j) => j.status === 'queued').length ?? 0;
  const subtitle =
    running || queued
      ? [running && `${running} rendering`, queued && `${queued} in line`].filter(Boolean).join(' · ')
      : jobs.data
        ? 'All caught up'
        : undefined;

  const banners: { tone: Tone; text: string }[] = [];
  if (notice.data?.text)
    banners.push({
      tone: notice.data.maintenance || notice.data.level === 'warning' ? 'warning' : 'info',
      text: notice.data.text,
    });
  if (jobs.data?.paused)
    banners.push({
      tone: 'warning',
      text: 'An admin paused the jobs. Yours wait in line and start when they resume.',
    });
  if (jobs.error) banners.push({ tone: 'danger', text: jobs.error.message });

  return (
    <TitledScreen
      title="Activity"
      back
      scrollY={scrollY}
      actions={
        <IconButton
          icon="add"
          label="Create"
          color={colors.onAccent}
          background={colors.accent}
          onPress={() => router.navigate('/create')}
        />
      }
    >
      <Animated.FlatList
        data={lines}
        keyExtractor={(line) => line.key}
        onScroll={onScroll}
        scrollEventThrottle={16}
        contentContainerStyle={styles.list}
        itemLayoutAnimation={LinearTransition.duration(200)}
        ListHeaderComponent={
          <View>
            <LargeTitle title="Activity" subtitle={subtitle} scrollY={scrollY} />
            {banners.length ? (
              <View style={styles.banners}>
                {banners.map((b) => (
                  <Banner key={b.text} tone={b.tone} text={b.text} />
                ))}
              </View>
            ) : null}
          </View>
        }
        renderItem={({ item, index }) =>
          item.type === 'section' ? (
            <Text style={styles.section}>{item.title}</Text>
          ) : (
            <Animated.View entering={FadeIn.duration(200)} exiting={FadeOut.duration(180)} style={styles.item}>
              <JobCard
                job={item.job}
                onRetry={(job) => retry.mutate(job)}
                onRemove={confirmRemove}
                retrying={retry.isPending && retry.variables?.id === item.job.id}
              />
            </Animated.View>
          )
        }
        ListEmptyComponent={
          jobs.isPending ? (
            <View style={styles.pad}>
              <JobSkeletons />
            </View>
          ) : (
            <EmptyState
              icon="layers-outline"
              title="Nothing in the Works"
              text="Start something here or in the studio, and watch it render live."
            >
              <Button label="Create Something" icon="sparkles" onPress={() => router.navigate('/create')} />
            </EmptyState>
          )
        }
        refreshControl={
          <RefreshControl
            refreshing={jobs.isRefetching && !jobs.isPending}
            onRefresh={() => {
              void jobs.refetch();
            }}
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
  pad: { paddingHorizontal: spacing.lg },
  banners: { gap: spacing.sm, paddingHorizontal: spacing.lg, marginBottom: spacing.sm },
  section: {
    ...fonts.title3,
    color: colors.text,
    paddingHorizontal: spacing.lg,
    marginTop: spacing.lg,
    marginBottom: spacing.md,
  },
  item: { paddingHorizontal: spacing.lg, marginBottom: spacing.md },
});
