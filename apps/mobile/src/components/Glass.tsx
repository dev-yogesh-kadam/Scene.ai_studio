import type { ReactNode } from 'react';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { colors } from '@/theme';

// The browser blurs whatever is behind (CSS backdrop-filter), as Apple's materials do. A browser that can't shows the
// translucent colour alone, which still reads.
const frosted = { backdropFilter: 'blur(24px) saturate(180%)', WebkitBackdropFilter: 'blur(24px) saturate(180%)' } as unknown as ViewStyle;

/** Frosted glass: a bar or panel over content. */
export function Glass({ children, style }: { children?: ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[styles.glass, frosted, style]}>{children}</View>;
}

const styles = StyleSheet.create({
  glass: { backgroundColor: colors.glass, overflow: 'hidden' },
});
