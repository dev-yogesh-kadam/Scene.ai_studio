import * as Haptics from '@/lib/haptics';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import Animated, { Easing, useAnimatedStyle, withTiming } from 'react-native-reanimated';

import { Icon, type IconName } from './Icon';
import { colors, fonts } from '@/theme';

type Option<T> = { value: T; label: string; icon?: IconName };

/** Apple's segmented control: a track with a raised thumb that slides to the chosen segment. */
export function Segmented<T extends string>({ options, value, onChange }: { options: Option<T>[]; value: T; onChange: (value: T) => void }) {
  const [width, setWidth] = useState(0);
  const index = Math.max(0, options.findIndex((o) => o.value === value));
  const segment = width ? (width - 4) / options.length : 0;
  const thumb = useAnimatedStyle(() => ({ transform: [{ translateX: withTiming(index * segment, { duration: 220, easing: Easing.out(Easing.cubic) }) }] }), [index, segment]);

  return (
    <View style={styles.track} onLayout={(e) => setWidth(e.nativeEvent.layout.width)}>
      {segment ? <Animated.View style={[styles.thumb, { width: segment }, thumb]} /> : null}
      {options.map((option) => {
        const on = option.value === value;
        return (
          <Pressable
            key={option.value}
            style={styles.segment}
            accessibilityRole="button"
            accessibilityState={{ selected: on }}
            onPress={() => {
              if (on) return;
              void Haptics.selectionAsync();
              onChange(option.value);
            }}>
            {option.icon ? <Icon name={option.icon} size={15} color={on ? colors.text : colors.textSecondary} /> : null}
            <Text style={[styles.label, on && styles.labelOn]}>{option.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  track: { flexDirection: 'row', backgroundColor: colors.fill, borderRadius: 10, padding: 2, height: 36 },
  thumb: {
    position: 'absolute',
    top: 2,
    bottom: 2,
    left: 2,
    borderRadius: 8,
    backgroundColor: colors.segmentThumb,
    shadowColor: '#000',
    shadowOpacity: 0.2,
    shadowRadius: 4,
    elevation: 2,
  },
  segment: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5 },
  label: { ...fonts.footnoteStrong, color: colors.textSecondary },
  labelOn: { color: colors.text },
});
