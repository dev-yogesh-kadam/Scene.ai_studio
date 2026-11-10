import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query';
import * as Haptics from '@/lib/haptics';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';

import { apiUrl } from '@scene/shared/api/client';
import { listLibrary, rateItem } from '@scene/shared/api/library';
import { getModule } from '@scene/shared/api/projects';
import { kit } from '@scene/shared/api/studio';
import { Banner } from '@/components/Banner';
import { Button, IconButton } from '@/components/Button';
import { EmptyState } from '@/components/EmptyState';
import { Icon, type IconName } from '@/components/Icon';
import { Segmented } from '@/components/Segmented';
import { Sheet } from '@/components/Sheet';
import { Skeleton } from '@/components/Skeleton';
import { Tap } from '@/components/Tap';
import { Thumb } from '@/components/Thumb';
import { LargeTitle, TitledScreen, useBarInset, useScrollY } from '@/components/TitledScreen';
import { useToast } from '@/components/Toast';
import { useColumns } from '@/hooks/useColumns';
import { clipLength, timeAgo } from '@scene/shared/format';
import { colors, fonts, lines, radius, spacing } from '@/theme';
import type { KitEntry, LibraryItem, LibraryPage, ModuleView } from '@scene/shared/types/api';

type View_ = 'story' | 'boards' | 'cast' | 'all';

const boardIcons: Record<string, IconName> = {
  outputs: 'film',
  characters: 'people',
  locations: 'location',
  props: 'cube',
  styles: 'color-palette',
};

export default function ModuleScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const moduleId = Number(id);
  const queryClient = useQueryClient();
  const { scrollY, onScroll } = useScrollY();
  const barInset = useBarInset();
  const view = useQuery({ queryKey: ['module', moduleId], queryFn: () => getModule(moduleId) });
  const data = view.data;
  const [tab, setTab] = useState<View_ | null>(null);
  // Start on the story when there is one, else on the boards, else everything.
  const shown: View_ = tab ?? (data?.shots.length ? 'story' : data?.boards.length ? 'boards' : 'all');

  /** Open an item in the player; with a queue, the player steps through it (a reel of shots, a stack's versions). */
  const open = (item: LibraryItem, queue?: LibraryItem[]) => {
    for (const each of queue ?? [item]) queryClient.setQueryData(['item', each.id], each);
    router.push({ pathname: '/watch/[id]', params: { id: String(item.id), ...(queue && queue.length > 1 ? { queue: queue.map((q) => q.id).join(',') } : {}) } });
  };

  const [chosen, setChosen] = useState<Record<number, number>>({});
  const featured = featuredOf(data);
  // Play Story plays the take you picked of each shot, else the one you starred, else the newest.
  const reel = data?.shots.map((s) => s.takes[takeIndex(s, chosen)]) ?? [];

  return (
    <TitledScreen
      title={data?.module.name ?? 'Module'}
      back
      scrollY={scrollY}
      actions={<IconButton icon="chatbubble-ellipses" label="Ask the agent" color={colors.onAccent} background={colors.accent} onPress={() => router.push({ pathname: '/chat/[id]', params: { id: String(moduleId) } })} />}>
      <Animated.ScrollView
        onScroll={onScroll}
        scrollEventThrottle={16}
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={view.isRefetching}
            onRefresh={() => {
              void view.refetch();
              void queryClient.invalidateQueries({ queryKey: ['module-items', moduleId] });
            }}
            progressViewOffset={barInset}
            tintColor={colors.textSecondary}
            colors={[colors.accent]}
            progressBackgroundColor={colors.surface}
          />
        }>
        <LargeTitle
          title={data?.module.name ?? ' '}
          subtitle={data ? [data.module.project.name, `${data.items} ${data.items === 1 ? 'item' : 'items'}`, data.updated ? timeAgo(data.updated) : null].filter(Boolean).join('  ·  ') : undefined}
          scrollY={scrollY}
        />

        {view.error ? (
          <View style={styles.pad}>
            <Banner tone="danger" text={view.error.message} />
          </View>
        ) : null}

        {view.isPending ? (
          <View style={[styles.pad, { gap: spacing.lg }]}>
            <Skeleton style={{ aspectRatio: 16 / 9, borderRadius: radius.lg }} />
            <Skeleton style={{ height: 36, borderRadius: 10 }} />
            <Skeleton style={{ height: 220, borderRadius: radius.lg }} />
          </View>
        ) : data ? (
          <View style={styles.body}>
            {featured ? (
              <Animated.View entering={FadeIn.duration(200)} style={styles.pad}>
                <Tap onPress={() => open(featured.item)} scaleTo={0.98} style={styles.hero} accessibilityLabel={`${featured.label.toLowerCase()}: ${featured.item.name}`} accessibilityHint="Plays it.">
                  <Thumb id={featured.item.id} kind={featured.item.kind} style={StyleSheet.absoluteFill} iconSize={48} />
                  <LinearGradient colors={['transparent', 'rgba(0,0,0,0.8)']} style={styles.heroShade} />
                  <View style={styles.heroPlay}>
                    <Icon name={featured.item.kind === 'image' ? 'expand' : 'play'} size={26} color="#000" />
                  </View>
                  <View style={styles.heroCaption}>
                    <Text style={styles.heroLabel}>{featured.label}</Text>
                    <Text style={styles.heroName} numberOfLines={1}>
                      {featured.item.name}
                    </Text>
                  </View>
                </Tap>
              </Animated.View>
            ) : null}

            <View style={[styles.pad, styles.actionsRow]}>
              {reel.length > 1 ? (
                <Button label="Play Story" icon="play" onPress={() => open(reel[0], reel)} style={{ flex: 1 }} />
              ) : null}
              <Button
                label="Ask Agent"
                icon="chatbubble-ellipses"
                variant={reel.length > 1 ? 'secondary' : 'primary'}
                onPress={() => router.push({ pathname: '/chat/[id]', params: { id: String(moduleId) } })}
                style={{ flex: 1 }}
              />
            </View>

            <View style={styles.pad}>
              <Segmented
                options={[
                  { value: 'story', label: `Story${data.shots.length ? ` ${data.shots.length}` : ''}` },
                  { value: 'boards', label: 'Boards' },
                  { value: 'cast', label: 'Cast' },
                  { value: 'all', label: 'All' },
                ]}
                value={shown}
                onChange={setTab}
              />
            </View>

            {shown === 'story' ? (
              <Story data={data} open={open} chosen={chosen} setChosen={setChosen} />
            ) : shown === 'boards' ? (
              <Boards data={data} open={open} />
            ) : shown === 'cast' ? (
              <Cast moduleId={moduleId} />
            ) : (
              <AllItems moduleId={moduleId} open={open} />
            )}
          </View>
        ) : null}
      </Animated.ScrollView>
    </TitledScreen>
  );
}

/** The one thing to show first: the newest cut on Outputs, else the last shot's newest take, else the newest item. */
function featuredOf(data?: ModuleView): { item: LibraryItem; label: string } | null {
  if (!data) return null;
  const outputs = data.boards.find((b) => b.name.toLowerCase() === 'outputs');
  if (outputs?.stacks[0]?.items[0]) return { item: outputs.stacks[0].items[0], label: 'LATEST CUT' };
  const shot = data.shots[data.shots.length - 1];
  if (shot) return { item: shot.takes[0], label: `SHOT ${shot.number} · LATEST` };
  const first = data.boards.flatMap((b) => b.stacks)[0]?.items[0];
  return first ? { item: first, label: 'LATEST' } : null;
}

type Open = (item: LibraryItem, queue?: LibraryItem[]) => void;
type Shot = ModuleView['shots'][number];

function takeIndex(shot: Shot, chosen: Record<number, number>) {
  if (chosen[shot.number] != null) return Math.min(chosen[shot.number], shot.takes.length - 1);
  const starred = shot.takes.findIndex((t) => t.rating > 0);
  return starred >= 0 ? starred : 0;
}

/** The story as a vertical storyboard: one card per shot, its takes in a strip under it. */
function Story({ data, open, chosen, setChosen }: { data: ModuleView; open: Open; chosen: Record<number, number>; setChosen: (c: Record<number, number>) => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  // Long-press a take: it becomes the shot's best take (starred), or stops being it.
  const star = async (take: LibraryItem) => {
    void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      await rateItem(take.id, take.rating > 0 ? 0 : 1);
      toast(take.rating > 0 ? 'No longer the best take' : 'Marked as the best take', { icon: take.rating > 0 ? 'star-outline' : 'star' });
      void queryClient.invalidateQueries({ queryKey: ['module', data.module.id] });
      void queryClient.invalidateQueries({ queryKey: ['library'] });
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), { tone: 'danger' });
    }
  };
  if (!data.shots.length) {
    return <EmptyState icon="film-outline" title="No Story Shots Yet" text="When the agent plans a film here, its shots line up in order, each with its takes." />;
  }
  const current = data.shots.map((s) => s.takes[takeIndex(s, chosen)]);
  return (
    <View style={[styles.pad, { gap: spacing.lg }]}>
      {data.shots.map((shot, index) => {
        const take = current[index];
        const length = take.kind === 'video' ? clipLength(take.seconds) : null;
        return (
          <Animated.View key={shot.number} entering={FadeIn.duration(200)} style={styles.shot}>
            <Tap
              onPress={() => open(take, current)}
              onLongPress={() => void star(take)}
              delayLongPress={320}
              scaleTo={0.98}
              accessibilityLabel={`Shot ${shot.number}, take ${shot.takes.length - takeIndex(shot, chosen)} of ${shot.takes.length}${take.rating > 0 ? ', best take' : ''}. ${take.prompt}`}
              accessibilityHint="Plays the story from here. Touch and hold to mark it as the best take.">
              <View style={styles.shotFrame}>
                <Thumb id={take.id} kind={take.kind} style={StyleSheet.absoluteFill} />
                <View style={styles.shotNumber}>
                  <Text style={styles.shotNumberText}>{shot.number}</Text>
                </View>
                {length ? (
                  <View style={styles.shotLength}>
                    <Icon name="play" size={10} color="#fff" />
                    <Text style={styles.shotLengthText}>{length}</Text>
                  </View>
                ) : null}
                {take.rating > 0 ? (
                  <View style={styles.shotStar}>
                    <Icon name="star" size={12} color={colors.star} />
                  </View>
                ) : null}
              </View>
            </Tap>
            <View style={styles.shotInfo}>
              <View style={styles.shotTitleRow}>
                <Text style={styles.shotTitle}>Shot {shot.number}</Text>
                <Text style={styles.shotTakes}>
                  {shot.takes.length > 1 ? `Take ${shot.takes.length - takeIndex(shot, chosen)} of ${shot.takes.length}` : '1 take'}
                </Text>
              </View>
              {take.prompt ? (
                <Text style={styles.shotPrompt} numberOfLines={2}>
                  {take.prompt}
                </Text>
              ) : null}
            </View>
            {shot.takes.length > 1 ? (
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.takes}>
                {shot.takes.map((t, i) => {
                  const on = i === takeIndex(shot, chosen);
                  return (
                    <Tap
                      key={t.id}
                      onPress={() => setChosen({ ...chosen, [shot.number]: i })}
                      onLongPress={() => void star(t)}
                      accessibilityLabel={`Take ${shot.takes.length - i} of ${shot.takes.length}${t.rating > 0 ? ', best take' : ''}`}
                      accessibilityState={{ selected: on }}
                      haptic="selection"
                      scaleTo={0.92}
                      style={[styles.take, on && styles.takeOn]}>
                      <Thumb id={t.id} kind={t.kind} style={styles.takeThumb} iconSize={16} />
                      {t.rating > 0 ? (
                        <View style={styles.takeStar}>
                          <Icon name="star" size={9} color={colors.star} />
                        </View>
                      ) : null}
                    </Tap>
                  );
                })}
              </ScrollView>
            ) : null}
          </Animated.View>
        );
      })}
    </View>
  );
}

/** The canvas's boards as shelves: a row of cards per board, each card a stack of versions. */
function Boards({ data, open }: { data: ModuleView; open: Open }) {
  if (!data.boards.length) {
    return <EmptyState icon="grid-outline" title="No Boards Yet" text="Characters, locations, props and finished cuts the agent makes land on boards here." />;
  }
  return (
    <View style={{ gap: spacing.xl }}>
      {data.boards.map((board, b) => (
        <Animated.View key={board.name} entering={FadeIn.duration(200)} style={{ gap: spacing.md }}>
          <View style={[styles.pad, styles.boardHeader]}>
            <View style={styles.boardIcon}>
              <Icon name={boardIcons[board.name.toLowerCase()] ?? 'albums'} size={15} color={colors.accent} />
            </View>
            <Text style={styles.boardName}>{board.name}</Text>
            <Text style={styles.boardCount}>{board.stacks.length}</Text>
          </View>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.shelf}>
            {board.stacks.map((stack) => {
              const top = stack.items[0];
              return (
                <Tap
                  key={stack.group}
                  onPress={() => open(top, stack.items)}
                  scaleTo={0.95}
                  style={styles.stack}
                  accessibilityLabel={`${top.name}${stack.items.length > 1 ? `, ${stack.items.length} versions` : ''}`}>
                  <View>
                    {stack.items.length > 1 ? <View style={styles.stackBehind} /> : null}
                    <Thumb id={top.id} kind={top.kind} style={styles.stackThumb} />
                    {stack.items.length > 1 ? (
                      <View style={styles.versions}>
                        <Icon name="layers" size={11} color="#fff" />
                        <Text style={styles.versionsText}>{stack.items.length}</Text>
                      </View>
                    ) : null}
                  </View>
                  <Text style={styles.stackName} numberOfLines={1}>
                    {top.name}
                  </Text>
                </Tap>
              );
            })}
          </ScrollView>
        </Animated.View>
      ))}
    </View>
  );
}

const castIcons: Record<string, IconName> = {
  character: 'person',
  location: 'location',
  outfit: 'shirt',
  prop: 'cube',
  voice: 'mic',
  style: 'color-palette',
  script: 'document-text',
};

/** The module's NeuralCore: who and what the agent keeps the same from shot to shot, with the picture it uses. */
function Cast({ moduleId }: { moduleId: number }) {
  const entries = useQuery({ queryKey: ['kit', moduleId], queryFn: () => kit(moduleId) });
  const [open, setOpen] = useState<KitEntry | null>(null);
  const { cell } = useColumns(3);
  if (entries.isPending) return <ActivityIndicator color={colors.textSecondary} style={{ marginTop: spacing.xl }} />;
  const shown = (entries.data?.entries ?? []).filter((e) => !e.hidden);
  if (!shown.length) {
    return <EmptyState icon="people-outline" title="No Cast Yet" text="Characters, places and props saved to NeuralCore show here, so every shot keeps them the same." />;
  }
  return (
    <View style={[styles.pad, styles.castGrid]}>
      {shown.map((entry, i) => (
        <Animated.View key={entry.id} entering={FadeIn.duration(200)} style={{ width: cell }}>
          <Tap onPress={() => setOpen(entry)} scaleTo={0.95} accessibilityLabel={`${entry.name}, ${entry.type}${entry.always ? ', in every shot' : ''}`}>
            <View style={styles.castPicture}>
              {entry.kind === 'image' || entry.kind === 'video' ? (
                <Image source={{ uri: apiUrl(entry.url) }} style={StyleSheet.absoluteFill} contentFit="cover" transition={200} />
              ) : (
                <Icon name={castIcons[entry.type] ?? 'sparkles'} size={30} color={colors.textMuted} />
              )}
              {entry.always ? (
                <View style={styles.castAlways}>
                  <Icon name="pin" size={10} color={colors.onAccent} />
                </View>
              ) : null}
            </View>
            <Text style={styles.castName} numberOfLines={1}>
              {entry.name}
            </Text>
            <Text style={styles.castType} numberOfLines={1}>
              {entry.type.charAt(0).toUpperCase() + entry.type.slice(1)}
              {entry.variant ? ` · ${entry.variant}` : ''}
            </Text>
          </Tap>
        </Animated.View>
      ))}
      <Sheet open={!!open} onClose={() => setOpen(null)} title={open?.name}>
        {open ? (
          <View style={{ gap: spacing.lg }}>
            {open.kind === 'image' ? <Image source={{ uri: apiUrl(open.url) }} style={styles.castLarge} contentFit="cover" /> : null}
            {open.about ? <Text style={styles.castAbout}>{open.about}</Text> : null}
            {open.use_note ? (
              <View style={styles.castNote}>
                <Text style={styles.castNoteLabel}>HOW IT IS USED</Text>
                <Text style={styles.castAbout}>{open.use_note}</Text>
              </View>
            ) : null}
            {open.palette ? <Text style={styles.castType}>Palette: {open.palette}</Text> : null}
            <Text style={styles.castType}>{open.always ? 'In every shot of this module' : 'Used when a shot calls for it'}</Text>
          </View>
        ) : null}
      </Sheet>
    </View>
  );
}

/** Everything in the module, in a dense grid, a page at a time. */
function AllItems({ moduleId, open }: { moduleId: number; open: Open }) {
  const items = useInfiniteQuery({
    queryKey: ['module-items', moduleId],
    queryFn: ({ pageParam }) => listLibrary({ project: moduleId, exact: true, limit: 60 }, pageParam),
    initialPageParam: 0,
    getNextPageParam: (last: LibraryPage) => last.next_offset ?? undefined,
  });
  const all = items.data?.pages.flatMap((p) => p.items) ?? [];
  const { cell } = useColumns(3, 3);
  if (items.isPending) return <ActivityIndicator color={colors.textSecondary} style={{ marginTop: spacing.xl }} />;
  if (!all.length) return <EmptyState icon="albums-outline" title="Nothing Here Yet" />;
  return (
    <View style={styles.pad}>
      <View style={styles.dense}>
        {all.map((item) => (
          <Tap key={item.id} onPress={() => open(item)} scaleTo={0.94} style={[styles.denseCell, { width: cell }]} accessibilityLabel={`${item.name}, ${item.kind}`}>
            <Thumb id={item.id} kind={item.kind} style={StyleSheet.absoluteFill} iconSize={22} />
            {item.rating > 0 ? (
              <View style={styles.denseStar}>
                <Icon name="star" size={10} color={colors.star} />
              </View>
            ) : null}
          </Tap>
        ))}
      </View>
      {items.hasNextPage ? (
        <Button
          variant="secondary"
          label="Show More"
          busy={items.isFetchingNextPage}
          onPress={() => void items.fetchNextPage()}
          style={{ marginTop: spacing.lg }}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  content: { paddingBottom: spacing.xxl * 2 },
  body: { gap: spacing.xl },
  pad: { paddingHorizontal: spacing.lg },
  hero: { aspectRatio: 16 / 9, borderRadius: radius.lg, overflow: 'hidden', backgroundColor: colors.surface, justifyContent: 'flex-end' },
  heroShade: { position: 'absolute', left: 0, right: 0, bottom: 0, height: '60%' },
  heroPlay: {
    position: 'absolute',
    alignSelf: 'center',
    top: '50%',
    marginTop: -28,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: 'rgba(255,255,255,0.92)',
    alignItems: 'center',
    justifyContent: 'center',
    paddingLeft: 3,
  },
  heroCaption: { padding: spacing.lg, gap: 2 },
  heroLabel: { ...fonts.caption2, color: 'rgba(255,255,255,0.75)', letterSpacing: 0.6 },
  heroName: { ...fonts.headline, color: '#fff' },
  shot: { backgroundColor: colors.surface, borderRadius: radius.lg, overflow: 'hidden' },
  shotFrame: { aspectRatio: 16 / 9, backgroundColor: colors.surfaceRaised },
  shotNumber: {
    position: 'absolute',
    top: spacing.md,
    left: spacing.md,
    minWidth: 28,
    height: 28,
    borderRadius: 14,
    paddingHorizontal: 8,
    backgroundColor: 'rgba(0,0,0,0.6)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  shotNumberText: { ...fonts.footnoteStrong, color: '#fff' },
  shotLength: {
    position: 'absolute',
    right: spacing.md,
    bottom: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    backgroundColor: 'rgba(0,0,0,0.6)',
    borderRadius: radius.pill,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  shotLengthText: { ...fonts.caption2, color: '#fff' },
  shotStar: { position: 'absolute', top: spacing.md, right: spacing.md, backgroundColor: 'rgba(0,0,0,0.6)', borderRadius: radius.pill, padding: 5 },
  shotInfo: { padding: spacing.lg, paddingBottom: spacing.md, gap: 4 },
  shotTitleRow: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' },
  shotTitle: { ...fonts.headline, color: colors.text },
  shotTakes: { ...fonts.footnote, color: colors.textSecondary },
  shotPrompt: { ...fonts.subhead, color: colors.textSecondary },
  takes: { paddingHorizontal: spacing.lg, paddingBottom: spacing.lg, gap: spacing.sm },
  take: { borderRadius: 8, borderWidth: 2, borderColor: 'transparent', padding: 1 },
  takeOn: { borderColor: colors.accent },
  takeThumb: { width: 72, height: 41, borderRadius: 6 },
  boardHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  boardIcon: { width: 26, height: 26, borderRadius: 7, backgroundColor: colors.accentSoft, alignItems: 'center', justifyContent: 'center' },
  boardName: { ...fonts.title3, color: colors.text, flex: 1 },
  boardCount: { ...fonts.subhead, color: colors.textSecondary },
  shelf: { paddingHorizontal: spacing.lg, gap: spacing.md },
  stack: { width: 148 },
  stackBehind: { position: 'absolute', top: -5, left: 8, right: 8, height: 20, borderRadius: radius.md, backgroundColor: colors.surfaceRaised },
  stackThumb: { width: 148, height: 148, borderRadius: radius.md },
  versions: {
    position: 'absolute',
    right: 8,
    bottom: 8,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    backgroundColor: 'rgba(0,0,0,0.6)',
    borderRadius: radius.pill,
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  versionsText: { ...fonts.caption2, color: '#fff' },
  stackName: { ...fonts.subheadStrong, color: colors.text, marginTop: spacing.sm },
  actionsRow: { flexDirection: 'row', gap: spacing.sm },
  takeStar: { position: 'absolute', right: 4, top: 4 },
  castGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md, rowGap: spacing.lg },
  castCell: { width: '30.5%' },
  castPicture: { aspectRatio: 1, borderRadius: 999, overflow: 'hidden', backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' },
  castAlways: { position: 'absolute', right: 6, bottom: 6, width: 20, height: 20, borderRadius: 10, backgroundColor: colors.accent, alignItems: 'center', justifyContent: 'center' },
  castName: { ...fonts.footnoteStrong, color: colors.text, textAlign: 'center', marginTop: spacing.sm },
  castType: { ...fonts.caption, color: colors.textSecondary, textAlign: 'center' },
  castLarge: { aspectRatio: 1, borderRadius: radius.lg },
  castAbout: { ...fonts.callout, color: colors.text, lineHeight: lines(23) },
  castNote: { backgroundColor: colors.surfaceRaised, borderRadius: radius.md, padding: spacing.md, gap: 4 },
  castNoteLabel: { ...fonts.caption2, color: colors.textSecondary, letterSpacing: 0.5 },
  dense: { flexDirection: 'row', flexWrap: 'wrap', gap: 3, borderRadius: radius.md, overflow: 'hidden' },
  denseCell: { width: '32.6%', aspectRatio: 1, backgroundColor: colors.surface },
  denseStar: { position: 'absolute', left: 4, bottom: 4 },
});
