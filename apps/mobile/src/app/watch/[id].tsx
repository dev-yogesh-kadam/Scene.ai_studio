import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEvent, useEventListener } from 'expo';
import * as Clipboard from 'expo-clipboard';
import * as Haptics from '@/lib/haptics';
import { router, useLocalSearchParams } from 'expo-router';
import { useVideoPlayer, VideoView } from 'expo-video';
import { useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, { FadeIn, runOnJS, useAnimatedStyle, withTiming } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { deleteItem, fileUrl, getItem, itemText, posterUrl, rateItem, renameItem, shareLink, stopSharing } from '@scene/shared/api/library';
import { Button, IconButton } from '@/components/Button';
import { Glass } from '@/components/Glass';
import { Group, Row } from '@/components/Group';
import { Icon, kindIcons, type IconName } from '@/components/Icon';
import { Sheet } from '@/components/Sheet';
import { ZoomImage } from '@/components/ZoomImage';
import { Tap } from '@/components/Tap';
import { useToast } from '@/components/Toast';
import { clipLength, credits, fileSize, timeAgo } from '@scene/shared/format';
import { download, share, shareLink as shareUrl } from '@/lib/media';
import { colors, fonts, kindColors, lines, radius, spacing } from '@/theme';
import type { LibraryItem } from '@scene/shared/types/api';
import { Alert } from '@/lib/dialog';

export default function WatchScreen() {
  const { id, queue: queued } = useLocalSearchParams<{ id: string; queue?: string }>();
  const itemId = Number(id);
  // A queue (a module's story, a stack's versions) is stepped through here: Previous and Next, and a video that ends
  // goes on to the next one.
  const queue = (queued ?? '').split(',').map(Number).filter(Boolean);
  const place = queue.indexOf(itemId);
  const go = (step: number) => {
    const next = queue[place + step];
    if (next) {
      void Haptics.selectionAsync();
      router.setParams({ id: String(next) });
    }
  };
  const queryClient = useQueryClient();
  const toast = useToast();
  const insets = useSafeAreaInsets();
  const item = useQuery({ queryKey: ['item', itemId], queryFn: () => getItem(itemId) });
  const [zoomed, setZoomed] = useState(false);
  const [busy, setBusy] = useState<'share' | 'save' | null>(null);
  const [infoOpen, setInfoOpen] = useState(false);
  const [chrome, setChrome] = useState(true);

  const chromeStyle = useAnimatedStyle(() => ({ opacity: withTiming(chrome ? 1 : 0, { duration: 220 }) }), [chrome]);

  const star = useMutation({
    mutationFn: (current: LibraryItem) => rateItem(current.id, current.rating > 0 ? 0 : 1),
    onMutate: (current) => {
      void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      queryClient.setQueryData(['item', itemId], { ...current, rating: current.rating > 0 ? 0 : 1 });
    },
    onError: (error, current) => {
      queryClient.setQueryData(['item', itemId], current);
      Alert.alert("Couldn't Change the Star", error.message);
    },
    onSettled: () => void queryClient.invalidateQueries({ queryKey: ['library'] }),
  });

  function askShare(current: LibraryItem) {
    Alert.alert('Share', 'Send the file itself, or a link anyone can open without signing in.', [
      { text: 'Send the File', onPress: () => void run('share', current) },
      { text: 'Send a Link', onPress: () => void sendLink(current) },
      { text: 'Cancel', style: 'cancel' },
    ]);
  }

  async function sendLink(current: LibraryItem) {
    setBusy('share');
    try {
      const link = await shareLink(current.id);
      const until = new Date(link.expires * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
      const how = await shareUrl(link.url, current.name);
      toast(how === 'copied' ? `Link copied · works until ${until}` : `Link works until ${until}`, { icon: 'link' });
    } catch (error) {
      Alert.alert("Couldn't Make a Link", error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(null);
    }
  }

  async function run(kind: 'share' | 'save', current: LibraryItem) {
    setBusy(kind);
    try {
      // The file through the share sheet where the browser can; else it is downloaded, to share from Downloads.
      if (kind === 'share' && (await share(current))) return;
      download(current);
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      toast('Downloading', { icon: 'download' });
    } catch (error) {
      Alert.alert(kind === 'share' ? "Couldn't Share" : "Couldn't Save", error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(null);
    }
  }

  const current = item.data;
  const tappable = current && current.kind !== 'video';
  const swipe = Gesture.Pan()
    .enabled(place >= 0 && queue.length > 1 && !zoomed)
    .activeOffsetX([-24, 24])
    .failOffsetY([-18, 18])
    .onEnd((e) => {
      if (e.translationX < -70 || e.velocityX < -700) runOnJS(go)(1);
      else if (e.translationX > 70 || e.velocityX > 700) runOnJS(go)(-1);
    });
  return (
    <View style={[styles.page, current?.kind !== 'video' && { backgroundColor: colors.background }]}>
      <View style={styles.stage}>
        <GestureDetector gesture={swipe}>
        <Pressable style={styles.stage} disabled={!tappable || current?.kind === 'image'} onPress={() => setChrome(!chrome)}>
          {current ? (
            <Viewer
              key={current.id}
              item={current}
              onEnded={place >= 0 && place < queue.length - 1 ? () => go(1) : undefined}
              onZoomed={setZoomed}
              onTap={() => setChrome(!chrome)}
            />
          ) : (
            <ActivityIndicator color={colors.textSecondary} />
          )}
        </Pressable>
        </GestureDetector>
      </View>

      <Animated.View style={[styles.top, chromeStyle]} pointerEvents={chrome ? 'box-none' : 'none'}>
        <Glass style={[styles.topBar, { paddingTop: insets.top + spacing.sm }]}>
          <IconButton icon="chevron-down" label="Close" onPress={() => router.back()} />
          <View style={styles.titleBox}>
            <Text style={styles.title} numberOfLines={1}>
              {current?.name ?? ''}
            </Text>
            {current ? (
              <Text style={styles.subtitle} numberOfLines={1}>
                {[place >= 0 && queue.length > 1 ? `${place + 1} of ${queue.length}` : null, current.workflow_title, timeAgo(current.created)]
                  .filter(Boolean)
                  .join(' · ')}
              </Text>
            ) : null}
          </View>
          <IconButton icon="ellipsis-horizontal" label="Details" onPress={() => setInfoOpen(true)} />
        </Glass>
      </Animated.View>

      {place >= 0 && queue.length > 1 ? (
        <Animated.View style={[styles.steps, chromeStyle]} pointerEvents={chrome ? 'box-none' : 'none'}>
          {place > 0 ? <IconButton icon="chevron-back" label="Previous" background="rgba(0,0,0,0.45)" size={42} onPress={() => go(-1)} /> : <View />}
          {place < queue.length - 1 ? <IconButton icon="chevron-forward" label="Next" background="rgba(0,0,0,0.45)" size={42} onPress={() => go(1)} /> : <View />}
        </Animated.View>
      ) : null}

      {item.error ? (
        <View style={styles.errorBox}>
          <Text style={styles.errorText}>{item.error.message}</Text>
        </View>
      ) : null}

      {current ? (
        <Animated.View style={[styles.bottom, chromeStyle]} pointerEvents={chrome ? 'box-none' : 'none'}>
          <Glass style={[styles.toolbar, { paddingBottom: insets.bottom + spacing.sm }]}>
            <Action
              icon={current.rating > 0 ? 'star' : 'star-outline'}
              label={current.rating > 0 ? 'Best Take' : 'Star'}
              color={current.rating > 0 ? colors.star : colors.text}
              onPress={() => star.mutate(current)}
              pop={current.rating > 0}
            />
            <Action icon="share-outline" label="Share" busy={busy === 'share'} onPress={() => askShare(current)} />
            {current.kind === 'text' ? (
              <Action
                icon="copy-outline"
                label="Copy"
                onPress={async () => {
                  await Clipboard.setStringAsync(await itemText(current.id));
                  toast('Copied', { icon: 'copy' });
                }}
              />
            ) : (
              <Action icon="arrow-down-circle-outline" label="Download" busy={busy === 'save'} onPress={() => run('save', current)} />
            )}
            <Action
              icon="sparkles-outline"
              label="Remix"
              onPress={() => router.navigate({ pathname: '/create', params: { workflow: current.workflow, prompt: current.prompt } })}
            />
          </Glass>
        </Animated.View>
      ) : null}

      {current ? <Details item={current} open={infoOpen} onClose={() => setInfoOpen(false)} /> : null}
    </View>
  );
}

/** Where to read an item's file: the studio, signed in by the session cookie. */
function sourceOf(item: LibraryItem) {
  return { uri: fileUrl(item.id) };
}

function Viewer({ item, onEnded, onZoomed, onTap }: { item: LibraryItem; onEnded?: () => void; onZoomed?: (zoomed: boolean) => void; onTap?: () => void }) {
  if (item.kind === 'text') return <TextViewer item={item} />;
  if (item.kind === 'image') {
    return <ZoomImage source={sourceOf(item)} placeholder={{ uri: posterUrl(item.id) }} onZoomed={onZoomed} onTap={onTap} />;
  }
  return <Player item={item} onEnded={onEnded} />;
}

/** A transcript: its words, to read and select. */
function TextViewer({ item }: { item: LibraryItem }) {
  const words = useQuery({ queryKey: ['item-text', item.id], queryFn: () => itemText(item.id) });
  if (words.isPending) return <ActivityIndicator color={colors.textSecondary} />;
  return (
    <ScrollView style={StyleSheet.absoluteFill} contentContainerStyle={styles.textPage}>
      <Text style={styles.textBody} selectable>
        {words.error ? words.error.message : words.data}
      </Text>
    </ScrollView>
  );
}

/** Video and sound both play through expo-video; sound gets big play controls of its own. */
function Player({ item, onEnded }: { item: LibraryItem; onEnded?: () => void }) {
  const player = useVideoPlayer(sourceOf(item), (p) => {
    p.loop = item.kind === 'video' && !onEnded;   // in a queue it goes on to the next one instead
    p.play();
  });
  useEventListener(player, 'playToEnd', () => onEnded?.());
  const { isPlaying } = useEvent(player, 'playingChange', { isPlaying: player.playing });
  const { status } = useEvent(player, 'statusChange', { status: player.status });

  if (item.kind === 'audio') {
    const tint = kindColors.audio;
    return (
      <View style={styles.audio}>
        <Animated.View entering={FadeIn.duration(200)} style={[styles.artwork, { shadowColor: tint }]}>
          <View style={[StyleSheet.absoluteFill, { backgroundColor: tint + '30', borderRadius: radius.xl }]} />
          <Icon name={kindIcons.audio} size={84} color={tint} />
        </Animated.View>
        <Text style={styles.audioTitle} numberOfLines={2}>
          {item.name}
        </Text>
        <View style={styles.audioRow}>
          <Tap onPress={() => player.seekBy(-10)} hitSlop={10} scaleTo={0.85}>
            <Icon name="play-back" size={30} color={colors.text} />
          </Tap>
          <Tap onPress={() => (isPlaying ? player.pause() : player.play())} scaleTo={0.9} haptic="light" style={styles.audioButton} accessibilityLabel={isPlaying ? 'Pause' : 'Play'}>
            {status === 'loading' ? <ActivityIndicator color={colors.background} /> : <Icon name={isPlaying ? 'pause' : 'play'} size={36} color={colors.background} />}
          </Tap>
          <Tap onPress={() => player.seekBy(10)} hitSlop={10} scaleTo={0.85}>
            <Icon name="play-forward" size={30} color={colors.text} />
          </Tap>
        </View>
        <Text style={styles.audioLength}>{clipLength(item.seconds) ?? ''}</Text>
      </View>
    );
  }
  return (
    <>
      <VideoView player={player} style={styles.video} contentFit="contain" nativeControls fullscreenOptions={{ enable: true }} />
      {status === 'loading' ? <ActivityIndicator color={colors.textSecondary} style={StyleSheet.absoluteFill} /> : null}
      {status === 'error' ? (
        <View style={styles.errorBox}>
          <Text style={styles.errorText}>This video can&apos;t be played here. Try Download or Share instead.</Text>
        </View>
      ) : null}
    </>
  );
}

function Action({ icon, label, onPress, busy, color = colors.text, pop }: { icon: IconName; label: string; onPress: () => void; busy?: boolean; color?: string; pop?: boolean }) {
  return (
    <Tap onPress={onPress} disabled={busy} scaleTo={0.85} style={styles.action} accessibilityLabel={label}>
      <View style={styles.actionIcon}>
        {busy ? (
          <ActivityIndicator color={colors.text} />
        ) : (
          <Animated.View key={`${icon}-${pop}`} entering={pop ? FadeIn : FadeIn.duration(120)}>
            <Icon name={icon} size={26} color={color} />
          </Animated.View>
        )}
      </View>
      <Text style={styles.actionLabel}>{label}</Text>
    </Tap>
  );
}

/** What it was made from and with, plus rename, delete and copy prompt. */
function Details({ item, open, onClose }: { item: LibraryItem; open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState(item.name);
  const [renaming, setRenaming] = useState(false);

  const rename = useMutation({
    mutationFn: () => renameItem(item.id, name.trim()),
    onSuccess: () => {
      queryClient.setQueryData(['item', item.id], { ...item, name: name.trim() });
      void queryClient.invalidateQueries({ queryKey: ['library'] });
      setRenaming(false);
      toast('Renamed', { icon: 'pencil' });
    },
    onError: (error) => Alert.alert("Couldn't Rename", error.message),
  });

  const remove = useMutation({
    mutationFn: () => deleteItem(item.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['library'] });
      onClose();
      router.back();
      toast('Deleted', { icon: 'trash' });
    },
    onError: (error) => Alert.alert("Couldn't Delete", error.message),
  });

  const facts: [string, string | null][] = [
    ['Model', item.workflow_title || item.workflow],
    ['Made', new Date(item.created * 1000).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })],
    ['Length', item.kind === 'video' || item.kind === 'audio' ? clipLength(item.seconds) : null],
    ['Size', item.width && item.height ? `${item.width} × ${item.height}` : null],
    ['File', fileSize(item.size)],
    ['Cost', item.cost ? credits(item.cost) : null],
    ['Project', item.project_name],
    ['Made By', item.made_by ?? null],
  ];

  return (
    <Sheet open={open} onClose={onClose} title="Details">
      {renaming ? (
        <View style={styles.renameRow}>
          <TextInput style={styles.input} value={name} onChangeText={setName} autoFocus maxLength={80} onSubmitEditing={() => rename.mutate()} selectTextOnFocus />
          <Button small label="Done" onPress={() => rename.mutate()} busy={rename.isPending} disabled={!name.trim()} />
        </View>
      ) : (
        <Tap style={styles.nameRow} onPress={() => item.mine && setRenaming(true)} scaleTo={item.mine ? 0.98 : 1}>
          <Text style={styles.detailName}>{item.name}</Text>
          {item.mine ? <Icon name="pencil" size={16} color={colors.textSecondary} /> : null}
        </Tap>
      )}

      {item.prompt ? (
        <View style={styles.promptBox}>
          <Text style={styles.promptLabel}>PROMPT</Text>
          <Text style={styles.promptText} selectable>
            {item.prompt}
          </Text>
          <View style={styles.promptActions}>
            <Button
              small
              variant="secondary"
              icon="copy-outline"
              label="Copy"
              onPress={async () => {
                await Clipboard.setStringAsync(item.prompt);
                toast('Prompt Copied', { icon: 'copy' });
              }}
            />
            <Button
              small
              variant="tinted"
              icon="sparkles"
              label="Make Again"
              onPress={() => {
                onClose();
                router.navigate({ pathname: '/create', params: { workflow: item.workflow, prompt: item.prompt } });
              }}
            />
          </View>
        </View>
      ) : null}

      <Group>
        {facts
          .filter(([, value]) => value)
          .map(([label, value]) => (
            <Row key={label} title={label} detail={value ?? ''} />
          ))}
      </Group>

      <Group footer="Share links work for 30 days unless you stop them.">
        {item.mine ? (
          <Row
            icon="link"
            tint="#8E8E93"
            title="Stop Share Links"
            onPress={async () => {
              await stopSharing(item.id).catch(() => undefined);
              toast('Links Stopped', { icon: 'link' });
            }}
          />
        ) : null}
      </Group>

      {item.mine ? (
        <Group>
          <Row
            title="Delete"
            destructive
            onPress={() =>
              Alert.alert('Delete This?', 'It is removed from your library everywhere, in the studio too.', [
                { text: 'Cancel', style: 'cancel' },
                { text: 'Delete', style: 'destructive', onPress: () => remove.mutate() },
              ])
            }
          />
        </Group>
      ) : null}
    </Sheet>
  );
}

const styles = StyleSheet.create({
  // Nothing in the player may be wider than the screen: a wider video makes the browser zoom the whole page out.
  page: { flex: 1, backgroundColor: '#000', overflow: 'hidden' },
  // The stage fills the screen (alignSelf: a centred parent would shrink it to its content, and a video placed over
  // the whole stage has none, so it had no width and the video took its own).
  stage: { flex: 1, alignSelf: 'stretch', alignItems: 'center', justifyContent: 'center' },
  // On the web the style lands on the <video> itself, which keeps its own size unless given one: the edges alone
  // (absoluteFill) don't size it.
  video: { position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' },
  top: { position: 'absolute', top: 0, left: 0, right: 0 },
  topBar: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingHorizontal: spacing.lg, paddingBottom: spacing.md },
  titleBox: { flex: 1, alignItems: 'center' },
  title: { ...fonts.headline, color: colors.text },
  subtitle: { ...fonts.caption, color: colors.textSecondary },
  bottom: { position: 'absolute', bottom: 0, left: 0, right: 0 },
  steps: { position: 'absolute', top: '46%', left: spacing.md, right: spacing.md, flexDirection: 'row', justifyContent: 'space-between' },
  toolbar: { flexDirection: 'row', justifyContent: 'space-around', paddingTop: spacing.sm, paddingHorizontal: spacing.md },
  action: { alignItems: 'center', gap: 2, minWidth: 68, paddingVertical: 4 },
  actionIcon: { height: 32, justifyContent: 'center' },
  actionLabel: { ...fonts.caption2, color: colors.textSecondary, fontSize: 10 },
  errorBox: { position: 'absolute', left: spacing.xl, right: spacing.xl, top: '45%', backgroundColor: colors.surface, padding: spacing.lg, borderRadius: radius.md },
  errorText: { ...fonts.subhead, color: colors.text, textAlign: 'center' },
  textPage: { paddingHorizontal: spacing.xl, paddingTop: 120, paddingBottom: 140 },
  textBody: { ...fonts.body, color: colors.text, lineHeight: lines(26) },
  audio: { alignItems: 'center', gap: spacing.xl, paddingHorizontal: spacing.xxl },
  artwork: {
    width: 240,
    height: 240,
    borderRadius: radius.xl,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface,
    shadowOpacity: 0.5,
    shadowRadius: 40,
    shadowOffset: { width: 0, height: 16 },
    elevation: 20,
  },
  audioTitle: { ...fonts.title2, color: colors.text, textAlign: 'center' },
  audioRow: { flexDirection: 'row', alignItems: 'center', gap: 44 },
  audioButton: { width: 72, height: 72, borderRadius: 36, backgroundColor: colors.text, alignItems: 'center', justifyContent: 'center', paddingLeft: 3 },
  audioLength: { ...fonts.footnote, color: colors.textSecondary },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, justifyContent: 'center' },
  detailName: { ...fonts.title3, color: colors.text, flexShrink: 1, textAlign: 'center' },
  renameRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  input: { flex: 1, ...fonts.body, color: colors.text, backgroundColor: colors.surfaceRaised, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 44 },
  promptBox: { backgroundColor: colors.surfaceRaised, borderRadius: radius.md, padding: spacing.lg, gap: spacing.sm },
  promptLabel: { ...fonts.caption2, color: colors.textSecondary, letterSpacing: 0.6 },
  promptText: { ...fonts.callout, color: colors.text, lineHeight: lines(23) },
  promptActions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.xs },
});
