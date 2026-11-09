import { router } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import { Button, IconButton } from './Button';
import { Icon, kindIcons, type IconName } from './Icon';
import { ProgressBar } from './ProgressBar';
import { Tap } from './Tap';
import { Thumb } from './Thumb';
import { credits, timeAgo } from '@/lib/format';
import { progress, statusLine } from '@/lib/jobs';
import { colors, fonts, kindColors, radius, spacing } from '@/theme';
import type { Job } from '@/types/api';

const looks: Record<string, { color: string; icon: IconName; label: string }> = {
  running: { color: colors.accent, icon: 'sync', label: 'Rendering' },
  queued: { color: colors.warning, icon: 'time', label: 'Queued' },
  done: { color: colors.success, icon: 'checkmark-circle', label: 'Ready' },
  failed: { color: colors.danger, icon: 'alert-circle', label: 'Failed' },
  cancelled: { color: colors.textSecondary, icon: 'remove-circle', label: 'Cancelled' },
};

type Props = {
  job: Job;
  onRetry: (job: Job) => void;
  onRemove: (job: Job) => void;
  retrying?: boolean;
};

export function JobCard({ job, onRetry, onRemove, retrying }: Props) {
  const look = looks[job.status] ?? looks.cancelled;
  const first = job.items[0];
  const tint = kindColors[job.kind as keyof typeof kindColors] ?? colors.accent;
  const open = first ? () => router.push({ pathname: '/watch/[id]', params: { id: String(first.id) } }) : undefined;

  return (
    <Tap
      onPress={open}
      scaleTo={open ? 0.975 : 1}
      style={styles.card}
      accessibilityRole={open ? 'button' : 'summary'}
      accessibilityLabel={`${job.name}, ${look.label}. ${statusLine(job)}`}
      accessibilityHint={open ? 'Opens what it made.' : undefined}>
      <View style={styles.row}>
        {first ? (
          <View>
            <Thumb id={first.id} kind={first.kind} style={styles.thumb} iconSize={24} />
            {first.kind === 'video' ? (
              <View style={styles.play}>
                <Icon name="play" size={11} color="#fff" />
              </View>
            ) : null}
          </View>
        ) : (
          <View style={[styles.thumb, styles.kindBox, { backgroundColor: tint + '22' }]}>
            <Icon name={kindIcons[job.kind] ?? 'sparkles'} size={24} color={tint} />
          </View>
        )}

        <View style={styles.middle}>
          <View style={styles.titleRow}>
            <Text style={styles.name} numberOfLines={1}>
              {job.name}
            </Text>
            <View style={[styles.pill, { backgroundColor: look.color + '22' }]}>
              <Icon name={look.icon} size={11} color={look.color} />
              <Text style={[styles.pillText, { color: look.color }]}>{look.label}</Text>
            </View>
          </View>
          <Text style={[styles.status, job.status === 'failed' && { color: colors.danger }]} numberOfLines={2}>
            {statusLine(job)}
          </Text>
          <Text style={styles.meta} numberOfLines={1}>
            {[job.workflow_title, job.cost ? credits(job.cost) : null, timeAgo(job.finished ?? job.created)].filter(Boolean).join('  ·  ')}
          </Text>
        </View>
      </View>

      {job.status === 'running' ? <ProgressBar value={progress(job)} /> : null}

      {job.status === 'failed' || job.status === 'cancelled' ? (
        <View style={styles.actions}>
          <Button small variant="tinted" label={job.cost ? `Try again · ${credits(job.cost)}` : 'Try again'} icon="refresh" onPress={() => onRetry(job)} busy={retrying} />
          <IconButton icon="close" size={32} label="Remove from the list" onPress={() => onRemove(job)} color={colors.textSecondary} />
        </View>
      ) : job.status === 'queued' || job.status === 'running' ? (
        <View style={styles.actions}>
          <Button small variant="secondary" label={job.status === 'running' ? 'Stop' : 'Cancel'} onPress={() => onRemove(job)} />
        </View>
      ) : null}
    </Tap>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.md, gap: spacing.md },
  row: { flexDirection: 'row', gap: spacing.md, alignItems: 'center' },
  thumb: { width: 64, height: 64, borderRadius: radius.md },
  kindBox: { alignItems: 'center', justifyContent: 'center' },
  play: {
    position: 'absolute',
    right: 4,
    bottom: 4,
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: 'rgba(0,0,0,0.55)',
    alignItems: 'center',
    justifyContent: 'center',
    paddingLeft: 1,
  },
  middle: { flex: 1, gap: 2 },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  name: { ...fonts.headline, color: colors.text, flex: 1 },
  pill: { flexDirection: 'row', alignItems: 'center', gap: 3, paddingHorizontal: 7, paddingVertical: 3, borderRadius: radius.pill },
  pillText: { ...fonts.caption2 },
  status: { ...fonts.subhead, color: colors.text },
  meta: { ...fonts.footnote, color: colors.textSecondary },
  actions: { flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: spacing.sm },
});
