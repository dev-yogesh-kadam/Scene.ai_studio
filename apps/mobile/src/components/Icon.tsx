import Ionicons from '@expo/vector-icons/Ionicons';
import type { ComponentProps } from 'react';

import { colors } from '@/theme';

// Ionicons: drawn in the style of Apple's SF Symbols (filled for "on", outlined for "off").
export type IconName = ComponentProps<typeof Ionicons>['name'];

/** An icon. With `accessibilityLabel` it is a picture with that name (a meaning nothing else says, as a tile's star). */
export function Icon({
  name,
  size = 22,
  color = colors.text,
  accessibilityLabel,
}: {
  name: IconName;
  size?: number;
  color?: string;
  accessibilityLabel?: string;
}) {
  return accessibilityLabel ? (
    <Ionicons name={name} size={size} color={color} accessibilityRole="image" accessibilityLabel={accessibilityLabel} />
  ) : (
    <Ionicons name={name} size={size} color={color} />
  );
}

/** The icon for each kind of work. */
export const kindIcons: Record<string, IconName> = {
  video: 'film',
  image: 'image',
  audio: 'musical-notes',
  text: 'document-text',
};
