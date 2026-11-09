import { useWindowDimensions } from 'react-native';

import { spacing } from '@/theme';

/**
 * How many columns a grid gets, and how wide each is: `phone` on a phone, more on a tablet or a phone held sideways.
 * `gap` and `padding` are the grid's own, so the cells fill the row exactly.
 */
export function useColumns(phone: number, gap: number = spacing.md, padding: number = spacing.lg) {
  const { width } = useWindowDimensions();
  const columns = width >= 1000 ? phone + 2 : width >= 640 ? phone + 1 : phone;
  const cell = Math.floor((width - padding * 2 - gap * (columns - 1)) / columns);
  return { columns, cell, wide: width >= 640 };
}
