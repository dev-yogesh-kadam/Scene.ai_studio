import type { Tabs } from 'expo-router';
import type { ComponentProps } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Icon, type IconName } from './Icon';
import { Tap } from './Tap';
import { colors, fonts } from '@/theme';

type BarProps = Parameters<NonNullable<ComponentProps<typeof Tabs>['tabBar']>>[0];

// Filled when chosen, outlined when not, as on iOS.
const icons: Record<string, [IconName, IconName]> = {
  home: ['home', 'home-outline'],
  projects: ['folder', 'folder-outline'],
  create: ['sparkles', 'sparkles-outline'],
  library: ['albums', 'albums-outline'],
  skills: ['bulb', 'bulb-outline'],
};

/** An iOS-style tab bar: a material with a hairline on top, icons with small labels, the chosen one in the tint. */
export function TabBar({ state, descriptors, navigateToTab }: BarProps) {
  const insets = useSafeAreaInsets();
  return (
    <View accessibilityRole="tablist" style={[styles.bar, { paddingBottom: Math.max(insets.bottom, 8) }]}>
      {state.routes.map((route, index) => {
        const focused = state.index === index;
        const label = descriptors[route.key].options.title ?? route.name;
        const [on, off] = icons[route.name] ?? ['ellipse', 'ellipse-outline'];
        const color = focused ? colors.accent : colors.textSecondary;
        return (
          <Tap
            key={route.key}
            style={styles.tab}
            scaleTo={0.88}
            haptic={focused ? false : 'selection'}
            accessibilityRole="tab"
            accessibilityState={{ selected: focused }}
            accessibilityLabel={label}
            onPress={() => {
              if (!focused) navigateToTab(route.key);
            }}
          >
            <Icon name={focused ? on : off} size={25} color={color} />
            <Text style={[styles.label, { color }]}>{label}</Text>
          </Tap>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: 'row',
    backgroundColor: colors.chrome,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.separator,
    paddingTop: 6,
  },
  tab: { flex: 1, alignItems: 'center', gap: 2 },
  label: { ...fonts.caption2, fontSize: 10 },
});
