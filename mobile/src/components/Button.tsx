import { LinearGradient } from 'expo-linear-gradient';
import { ActivityIndicator, StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native';

import { Icon, type IconName } from './Icon';
import { Tap } from './Tap';
import { colors, fonts, gradient, radius, spacing } from '@/theme';

type Props = {
  label: string;
  onPress: () => void;
  /** primary: the brand gradient; secondary: grey fill; tinted: tint text on a soft tint; danger and plain: text only. */
  variant?: 'primary' | 'secondary' | 'tinted' | 'danger' | 'plain';
  icon?: IconName;
  busy?: boolean;
  disabled?: boolean;
  small?: boolean;
  style?: StyleProp<ViewStyle>;
};

const looks = {
  primary: { background: 'transparent', text: colors.onBrand },
  secondary: { background: colors.surfaceRaised, text: colors.text },
  tinted: { background: colors.accentSoft, text: colors.accent },
  danger: { background: colors.dangerSoft, text: colors.danger },
  plain: { background: 'transparent', text: colors.accent },
};

export function Button({ label, onPress, variant = 'primary', icon, busy, disabled, small, style }: Props) {
  const look = looks[variant];
  const content = busy ? (
    <ActivityIndicator color={look.text} size="small" />
  ) : (
    <View style={styles.inner}>
      {icon ? <Icon name={icon} size={small ? 15 : 19} color={look.text} /> : null}
      <Text style={[small ? styles.smallText : styles.text, { color: look.text }]}>{label}</Text>
    </View>
  );
  return (
    <Tap
      onPress={onPress}
      disabled={disabled || busy}
      haptic="light"
      scaleTo={small ? 0.94 : 0.97}
      style={[styles.button, small && styles.small, { backgroundColor: look.background }, style]}>
      {variant === 'primary' ? (
        <LinearGradient colors={gradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={StyleSheet.absoluteFill} />
      ) : null}
      {content}
    </Tap>
  );
}

/** A round icon-only button, for bars and the player. */
export function IconButton({
  icon,
  onPress,
  color = colors.text,
  background = colors.fill,
  size = 36,
  label,
}: {
  icon: IconName;
  onPress: () => void;
  color?: string;
  background?: string;
  size?: number;
  label: string;
}) {
  return (
    <Tap
      onPress={onPress}
      accessibilityLabel={label}
      hitSlop={8}
      haptic="light"
      scaleTo={0.88}
      style={[{ width: size, height: size, borderRadius: size / 2, backgroundColor: background }, styles.round]}>
      <Icon name={icon} size={size * 0.55} color={color} />
    </Tap>
  );
}

const styles = StyleSheet.create({
  button: {
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.md + 2,
    minHeight: 50,
    paddingHorizontal: spacing.xl,
    overflow: 'hidden',
  },
  small: { minHeight: 32, paddingHorizontal: spacing.md, borderRadius: radius.pill },
  inner: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  text: { ...fonts.headline },
  smallText: { ...fonts.footnoteStrong },
  round: { alignItems: 'center', justifyContent: 'center' },
});
