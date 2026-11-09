import { Children, Fragment, isValidElement, type ReactNode } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Icon, type IconName } from './Icon';
import { Tap } from './Tap';
import { colors, fonts, radius, spacing } from '@/theme';

/** An inset grouped section, as in iOS Settings: a caption above, rounded rows with hairlines between, a note below. */
export function Group({ title, footer, children }: { title?: string; footer?: string; children: ReactNode }) {
  const rows = Children.toArray(children).filter(isValidElement);
  return (
    <View style={styles.group}>
      {title ? (
        <Text style={styles.title} accessibilityRole="header">
          {title}
        </Text>
      ) : null}
      <View style={styles.card}>
        {rows.map((row, index) => (
          <Fragment key={row.key ?? index}>
            {index > 0 ? <View style={styles.separator} /> : null}
            {row}
          </Fragment>
        ))}
      </View>
      {footer ? <Text style={styles.footer}>{footer}</Text> : null}
    </View>
  );
}

type RowProps = {
  icon?: IconName;
  /** The coloured rounded square behind the icon, as Settings has. */
  tint?: string;
  title: string;
  detail?: string;
  /** Under the title, smaller. */
  subtitle?: string;
  right?: ReactNode;
  onPress?: () => void;
  chevron?: boolean;
  destructive?: boolean;
};

export function Row({ icon, tint = colors.accent, title, detail, subtitle, right, onPress, chevron, destructive }: RowProps) {
  const body = (
    <View style={styles.row}>
      {icon ? (
        <View style={[styles.iconBox, { backgroundColor: tint }]}>
          <Icon name={icon} size={17} color="#fff" />
        </View>
      ) : null}
      <View style={styles.texts}>
        <Text style={[styles.rowTitle, destructive && { color: colors.danger }]} numberOfLines={1}>
          {title}
        </Text>
        {subtitle ? (
          <Text style={styles.subtitle} numberOfLines={2}>
            {subtitle}
          </Text>
        ) : null}
      </View>
      {detail ? (
        <Text style={styles.detail} numberOfLines={1}>
          {detail}
        </Text>
      ) : null}
      {right}
      {chevron ? <Icon name="chevron-forward" size={18} color={colors.textMuted} /> : null}
    </View>
  );
  return onPress ? (
    <Tap onPress={onPress} scaleTo={0.985} haptic="light">
      {body}
    </Tap>
  ) : (
    body
  );
}

const styles = StyleSheet.create({
  group: { gap: 6 },
  title: { ...fonts.footnote, color: colors.textSecondary, textTransform: 'uppercase', paddingHorizontal: spacing.lg, letterSpacing: 0.2 },
  card: { backgroundColor: colors.surface, borderRadius: radius.md, overflow: 'hidden' },
  separator: { height: StyleSheet.hairlineWidth, backgroundColor: colors.separator, marginLeft: 58 },
  footer: { ...fonts.footnote, color: colors.textSecondary, paddingHorizontal: spacing.lg },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingHorizontal: spacing.lg, minHeight: 50, paddingVertical: 10 },
  iconBox: { width: 29, height: 29, borderRadius: 7, alignItems: 'center', justifyContent: 'center' },
  texts: { flex: 1 },
  rowTitle: { ...fonts.body, color: colors.text },
  subtitle: { ...fonts.footnote, color: colors.textSecondary, marginTop: 1 },
  detail: { ...fonts.body, color: colors.textSecondary, maxWidth: '55%' },
});
