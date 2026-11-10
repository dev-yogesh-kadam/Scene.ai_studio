import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as Haptics from '@/lib/haptics';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, RefreshControl, StyleSheet, TextInput, View } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';

import { listLibrary, rateItem, upload, type LibraryFilter } from '@scene/shared/api/library';
import { Banner } from '@/components/Banner';
import { Button, IconButton } from '@/components/Button';
import { ChipRow } from '@/components/Chip';
import { EmptyState } from '@/components/EmptyState';
import { Icon, type IconName } from '@/components/Icon';
import { ItemTile } from '@/components/ItemTile';
import { GridSkeletons } from '@/components/Skeleton';
import { Tap } from '@/components/Tap';
import { LargeTitle, TitledScreen, useBarInset, useScrollY } from '@/components/TitledScreen';
import { useToast } from '@/components/Toast';
import { useColumns } from '@/hooks/useColumns';
import { fromCamera, fromFiles, fromPhotos, type PhoneFile } from '@/lib/pick';
import { colors, fonts, radius, spacing } from '@/theme';
import type { LibraryItem, LibraryPage } from '@scene/shared/types/api';
import { Alert } from '@/lib/dialog';

type Filter = '' | 'video' | 'image' | 'audio' | 'text' | 'starred';

const FILTERS: { value: Filter; label: string; icon?: IconName }[] = [
  { value: '', label: 'All' },
  { value: 'video', label: 'Videos', icon: 'film' },
  { value: 'image', label: 'Images', icon: 'image' },
  { value: 'audio', label: 'Audio', icon: 'musical-notes' },
  { value: 'starred', label: 'Best Takes', icon: 'star' },
  { value: 'text', label: 'Text', icon: 'document-text' },
];

export default function LibraryScreen() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { scrollY, onScroll } = useScrollY();
  const barInset = useBarInset();
  const [filter, setFilter] = useState<Filter>('');
  const { columns, cell } = useColumns(2);
  const [typed, setTyped] = useState('');
  const [q, setQ] = useState('');

  // Search as you type, once typing pauses.
  useEffect(() => {
    const timer = setTimeout(() => setQ(typed), 350);
    return () => clearTimeout(timer);
  }, [typed]);

  const query: LibraryFilter = filter === 'starred' ? { starred: true, q } : { kind: filter, q };
  const library = useInfiniteQuery({
    queryKey: ['library', query],
    queryFn: ({ pageParam }) => listLibrary(query, pageParam),
    initialPageParam: 0,
    getNextPageParam: (last: LibraryPage) => last.next_offset ?? undefined,
  });
  const items = library.data?.pages.flatMap((page) => page.items) ?? [];

  // Long-press a tile: star it as the best take, or un-star it.
  const star = useMutation({
    mutationFn: (item: LibraryItem) => rateItem(item.id, item.rating > 0 ? 0 : 1),
    onMutate: (item) => {
      void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      toast(item.rating > 0 ? 'Removed from Best Takes' : 'Added to Best Takes', { icon: item.rating > 0 ? 'star-outline' : 'star' });
    },
    onSettled: () => void queryClient.invalidateQueries({ queryKey: ['library'] }),
  });

  // Bring a file from the phone into the library: a picture or video from Photos, a new picture, or any file.
  const add = useMutation({
    mutationFn: (file: PhoneFile) => upload({ uri: file.uri, name: file.name, type: file.type }),
    onMutate: () => toast('Uploading…', { icon: 'cloud-upload', tone: 'info' }),
    onSuccess: () => {
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      toast('Added to Your Library', { icon: 'checkmark-circle' });
      void queryClient.invalidateQueries({ queryKey: ['library'] });
    },
    onError: (error) => Alert.alert("Couldn't Upload", error.message),
  });
  const pickAndUpload = () => {
    const take = (how: () => Promise<PhoneFile | null>) => () =>
      void how()
        .then((file) => file && add.mutate(file))
        .catch((e: Error) => Alert.alert("Couldn't Open It", e.message));
    Alert.alert('Add to Library', 'Pictures, videos, sounds and scripts can be used in your next creations.', [
      { text: 'Photos', onPress: take(() => fromPhotos()) },
      { text: 'Take a Picture', onPress: take(fromCamera) },
      { text: 'Files', onPress: take(() => fromFiles()) },
      { text: 'Cancel', style: 'cancel' },
    ]);
  };

  // The player opens on the item with its neighbours in line, so a swipe goes to the next one.
  const open = (item: LibraryItem) => {
    const at = items.indexOf(item);
    const around = items.slice(Math.max(0, at - 30), at + 31);
    for (const each of around) queryClient.setQueryData(['item', each.id], each);
    router.push({ pathname: '/watch/[id]', params: { id: String(item.id), ...(around.length > 1 ? { queue: around.map((i) => i.id).join(',') } : {}) } });
  };

  const filtered = !!q || filter !== '';
  const count = items.length ? `${items.length}${library.hasNextPage ? '+' : ''} ${items.length === 1 ? 'item' : 'items'}` : undefined;

  return (
    <TitledScreen title="Library" scrollY={scrollY} actions={<IconButton icon="add" label="Add from your phone" onPress={pickAndUpload} />}>
      <Animated.FlatList
        data={items}
        keyExtractor={(item) => String(item.id)}
        key={columns}
        numColumns={columns}
        onScroll={onScroll}
        scrollEventThrottle={16}
        keyboardDismissMode="on-drag"
        columnWrapperStyle={styles.column}
        contentContainerStyle={styles.grid}
        ListHeaderComponent={
          <View style={styles.header}>
            <LargeTitle title="Library" subtitle={count} scrollY={scrollY} />
            <View style={styles.search}>
              <Icon name="search" size={18} color={colors.textSecondary} />
              <TextInput
                style={styles.searchInput}
                placeholder="Search names and prompts"
                placeholderTextColor={colors.textSecondary}
                value={typed}
                onChangeText={setTyped}
                returnKeyType="search"
              />
              {typed ? (
                <Tap onPress={() => setTyped('')} hitSlop={10}>
                  <Icon name="close-circle" size={18} color={colors.textSecondary} />
                </Tap>
              ) : null}
            </View>
            <ChipRow options={FILTERS} value={filter} onChange={setFilter} />
            {library.error ? (
              <View style={styles.error}>
                <Banner tone="danger" text={library.error.message} />
              </View>
            ) : null}
          </View>
        }
        renderItem={({ item, index }) => (
          <Animated.View entering={FadeIn.duration(300)} style={{ width: cell }}>
            <ItemTile item={item} onPress={() => open(item)} onLongPress={() => star.mutate(item)} />
          </Animated.View>
        )}
        onEndReached={() => {
          if (library.hasNextPage && !library.isFetchingNextPage) void library.fetchNextPage();
        }}
        onEndReachedThreshold={0.6}
        ListFooterComponent={library.isFetchingNextPage ? <ActivityIndicator color={colors.textSecondary} style={{ margin: spacing.lg }} /> : undefined}
        ListEmptyComponent={
          library.isPending ? (
            <GridSkeletons />
          ) : filtered ? (
            <EmptyState
              icon={filter === 'starred' ? 'star-outline' : 'search'}
              title={filter === 'starred' ? 'No Best Takes Yet' : 'No Results'}
              text={filter === 'starred' ? 'Long-press a tile, or tap the star in the player, to keep your favourites here.' : 'Try another word or filter.'}
            />
          ) : (
            <EmptyState icon="albums-outline" title="Your Library Is Empty" text="Everything you make lands here, ready to watch, share and save.">
              <Button label="Make Your First One" icon="sparkles" onPress={() => router.navigate('/create')} />
            </EmptyState>
          )
        }
        refreshControl={
          <RefreshControl
            refreshing={library.isRefetching && !library.isFetchingNextPage}
            onRefresh={() => void library.refetch()}
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
  header: { paddingBottom: spacing.lg, gap: spacing.md },
  search: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginHorizontal: spacing.lg,
    paddingHorizontal: 10,
    height: 38,
    backgroundColor: colors.fill,
    borderRadius: radius.sm + 2,
  },
  searchInput: { flex: 1, ...fonts.body, color: colors.text, paddingVertical: 0 },
  error: { paddingHorizontal: spacing.lg },
  grid: { paddingBottom: spacing.xxl, gap: spacing.xl },
  column: { gap: spacing.md, paddingHorizontal: spacing.lg },
  cell: { flex: 1 },
  lastOdd: { maxWidth: '50%', paddingRight: spacing.md / 2 },
});
