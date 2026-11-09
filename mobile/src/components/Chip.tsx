import { ScrollView, StyleSheet, Text } from 'react-native';

import { Icon, type IconName } from './Icon';
import { Tap } from './Tap';
import { colors, fonts, radius, spacing } from '@/theme';

type ChipProps = {
  label: string;
  selected?: boolean;
  onPress: () => void;
  icon?: IconName;
  /** A small note after the label, like a price. */
  note?: string;
};

/** A filter pill, as Apple Music and Photos have: grey, or white with dark text when chosen. */
export function Chip({ label, selected, onPress, icon, note }: ChipProps) {
  const color = selected ? colors.background : colors.text;
  return (
    <Tap onPress={onPress} haptic="selection" scaleTo={0.93} style={[styles.chip, selected && styles.selected]} accessibilityState={{ selected }}>
      {icon ? <Icon name={icon} size={14} color={color} /> : null}
      <Text style={[styles.label, { color }]}>{label}</Text>
      {note ? <Text style={[styles.note, { color }]}>{note}</Text> : null}
    </Tap>
  );
}

/** A row of chips that scrolls sideways when it doesn't fit. */
export function ChipRow<T extends string | number>({
  options,
  value,
  onChange,
  padded = true,
}: {
  options: { value: T; label: string; icon?: IconName; note?: string }[];
  value: T;
  onChange: (value: T) => void;
  padded?: boolean;
}) {
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={[styles.row, padded && styles.rowPadded]}
      keyboardShouldPersistTaps="handled">
      {options.map((option) => (
        <Chip
          key={String(option.value)}
          label={option.label}
          icon={option.icon}
          note={option.note}
          selected={option.value === value}
          onPress={() => onChange(option.value)}
        />
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 14,
    height: 34,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceRaised,
  },
  selected: { backgroundColor: colors.text },
  label: { ...fonts.subheadStrong },
  note: { ...fonts.caption, opacity: 0.6 },
  row: { gap: spacing.sm, alignItems: 'center' },
  rowPadded: { paddingHorizontal: spacing.lg },
});
