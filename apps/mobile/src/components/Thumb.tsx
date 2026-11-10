import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { useState } from 'react';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { Icon, kindIcons } from './Icon';
import { posterUrl } from '@scene/shared/api/library';
import { colors, kindColors } from '@/theme';

/** The poster of a library item (a still of a video, a small copy of a picture). Sound and text have no picture: a tinted symbol instead. */
export function Thumb({ id, kind, style, iconSize = 30 }: { id: number; kind: string; style?: StyleProp<ViewStyle>; iconSize?: number }) {
  const [failed, setFailed] = useState(false);
  const tint = kindColors[kind as keyof typeof kindColors] ?? colors.textSecondary;
  if (kind === 'audio' || kind === 'text' || failed) {
    return (
      <View style={[styles.box, style]} importantForAccessibility="no-hide-descendants">
        <LinearGradient colors={[tint + '40', tint + '12']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={StyleSheet.absoluteFill} />
        <Icon name={kindIcons[kind] ?? 'document'} size={iconSize} color={tint} />
      </View>
    );
  }
  return (
    <View style={[styles.box, style]} importantForAccessibility="no-hide-descendants">
      <Image
        source={{ uri: posterUrl(id) }}
        style={StyleSheet.absoluteFill}
        contentFit="cover"
        transition={250}
        cachePolicy="memory-disk"
        recyclingKey={String(id)}
        onError={() => setFailed(true)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  box: { backgroundColor: colors.surfaceRaised, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
});
