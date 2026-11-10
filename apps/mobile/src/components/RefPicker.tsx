import { useInfiniteQuery } from '@tanstack/react-query';
import { Image } from 'expo-image';
import { useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { Icon, kindIcons } from './Icon';
import { Sheet } from './Sheet';
import { Tap } from './Tap';
import { Thumb } from './Thumb';
import { listLibrary } from '@scene/shared/api/library';
import { fromCamera, fromFiles, fromPhotos, type PhoneFile } from '@/lib/pick';
import { colors, fonts, kindColors, radius, spacing } from '@/theme';
import type { ItemKind, LibraryItem, LibraryPage } from '@scene/shared/types/api';
import { Alert } from '@/lib/dialog';

/** What fills a reference slot: a file from the phone, or something already in the library. */
export type RefChoice = { phone: PhoneFile } | { item: LibraryItem };

/** "REFERENCE 1 (character, product…)" reads as "Reference 1". */
export function slotLabel(label: string) {
  const bare = label.replace(/\s*\(.*\)\s*$/, '').trim();
  return bare === bare.toUpperCase() ? bare.charAt(0) + bare.slice(1).toLowerCase() : bare;
}

type Props = {
  label: string;
  kind: string;
  optional: boolean;
  value: RefChoice | undefined;
  onChange: (value: RefChoice | undefined) => void;
};

/** One reference slot: empty, it offers Photos, Camera, Files or the Library; filled, it shows what was chosen. */
export function RefSlot({ label, kind, optional, value, onChange }: Props) {
  const [library, setLibrary] = useState(false);
  const tint = kindColors[kind as keyof typeof kindColors] ?? colors.accent;

  async function choose(how: 'photos' | 'camera' | 'files') {
    try {
      const file = how === 'photos' ? await fromPhotos(kind === 'video' ? 'video' : kind === 'image' ? 'image' : undefined) : how === 'camera' ? await fromCamera() : await fromFiles(kind === 'audio' ? ['audio/*', 'video/*'] : ['*/*']);
      if (file) onChange({ phone: file });
    } catch (e) {
      Alert.alert("Couldn't Open It", e instanceof Error ? e.message : String(e));
    }
  }

  function ask() {
    const options: [string, () => void][] = [
      ...(kind !== 'audio' ? ([['Photos', () => void choose('photos')]] as [string, () => void][]) : []),
      ...(kind === 'image' ? ([['Take a Picture', () => void choose('camera')]] as [string, () => void][]) : []),
      ['Files', () => void choose('files')],
      ['From Your Library', () => setLibrary(true)],
    ];
    Alert.alert(slotLabel(label), undefined, [...options.map(([text, onPress]) => ({ text, onPress })), { text: 'Cancel', style: 'cancel' as const }], { cancelable: true });
  }

  return (
    <>
      <Tap
        onPress={ask}
        scaleTo={0.95}
        style={styles.slot}
        accessibilityLabel={`${slotLabel(label)}${optional ? ', optional' : ''}: ${value ? ('item' in value ? value.item.name : value.phone.name) : 'empty'}`}
        accessibilityHint={value ? 'Choose another.' : 'Choose a file.'}>
        <View style={[styles.box, !value && { borderColor: optional ? colors.separator : tint, borderStyle: 'dashed' }]}>
          {value && 'item' in value ? (
            <Thumb id={value.item.id} kind={value.item.kind} style={StyleSheet.absoluteFill} iconSize={22} />
          ) : value && 'phone' in value && value.phone.kind === 'image' ? (
            <Image source={{ uri: value.phone.uri }} accessibilityLabel="" style={StyleSheet.absoluteFill} contentFit="cover" />
          ) : value ? (
            <Icon name={kindIcons[value.phone.kind] ?? 'document'} size={26} color={tint} />
          ) : (
            <Icon name="add" size={26} color={optional ? colors.textMuted : tint} />
          )}
          {value ? (
            <Tap onPress={() => onChange(undefined)} hitSlop={8} scaleTo={0.8} style={styles.clear} accessibilityLabel={`Remove ${slotLabel(label)}`}>
              <Icon name="close" size={12} color="#fff" />
            </Tap>
          ) : null}
        </View>
        <Text style={styles.label} numberOfLines={1}>
          {slotLabel(label)}
        </Text>
        <Text style={styles.kind} numberOfLines={1}>
          {value ? ('item' in value ? value.item.name : value.phone.name) : `${kind === 'audio' ? 'Sound' : kind === 'video' ? 'Video' : 'Picture'}${optional ? ' · optional' : ''}`}
        </Text>
      </Tap>
      <LibraryPicker
        open={library}
        kind={kind === 'audio' ? undefined : (kind as ItemKind)}
        onClose={() => setLibrary(false)}
        onPick={(item) => {
          setLibrary(false);
          onChange({ item });
        }}
      />
    </>
  );
}

/** Pick something from the library, in a sheet: a grid of the newest, of one kind. */
export function LibraryPicker({ open, kind, onClose, onPick }: { open: boolean; kind?: ItemKind; onClose: () => void; onPick: (item: LibraryItem) => void }) {
  const items = useInfiniteQuery({
    queryKey: ['library', { picker: kind ?? 'any' }],
    queryFn: ({ pageParam }) => listLibrary({ kind: kind ?? '', limit: 60 }, pageParam),
    initialPageParam: 0,
    getNextPageParam: (last: LibraryPage) => last.next_offset ?? undefined,
    enabled: open,
  });
  const all = items.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <Sheet open={open} onClose={onClose} title="Choose from Your Library">
      {items.isPending ? (
        <ActivityIndicator color={colors.textSecondary} style={{ margin: spacing.xl }} />
      ) : all.length ? (
        <View style={styles.grid}>
          {all.map((item) => (
            <Tap key={item.id} onPress={() => onPick(item)} scaleTo={0.92} style={styles.cell} accessibilityLabel={item.name}>
              <Thumb id={item.id} kind={item.kind} style={StyleSheet.absoluteFill} iconSize={20} />
            </Tap>
          ))}
        </View>
      ) : (
        <Text style={styles.kind}>Nothing of this kind in your library yet.</Text>
      )}
    </Sheet>
  );
}

const styles = StyleSheet.create({
  slot: { width: 104 },
  box: {
    width: 104,
    height: 104,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceRaised,
    borderWidth: 1.5,
    borderColor: 'transparent',
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  clear: { position: 'absolute', top: 6, right: 6, width: 22, height: 22, borderRadius: 11, backgroundColor: 'rgba(0,0,0,0.6)', alignItems: 'center', justifyContent: 'center' },
  label: { ...fonts.footnoteStrong, color: colors.text, marginTop: 6 },
  kind: { ...fonts.caption, color: colors.textSecondary },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 3, borderRadius: radius.md, overflow: 'hidden' },
  cell: { width: '32.6%', aspectRatio: 1, backgroundColor: colors.surfaceRaised },
});
