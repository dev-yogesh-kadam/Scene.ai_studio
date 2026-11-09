// Alerts and choices, drawn in the page: React Native's Alert does nothing in a browser. `Alert.alert(title, message,
// buttons)` works as it does on a phone; <DialogHost /> (in the root layout) shows them, one at a time.
import { useEffect, useState } from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, fonts, radius, spacing } from '@/theme';

type ButtonSpec = { text: string; style?: 'default' | 'cancel' | 'destructive'; onPress?: () => void };
type Dialog = { title: string; message?: string; buttons: ButtonSpec[] };

let show: ((dialog: Dialog) => void) | null = null;
const waiting: Dialog[] = [];

export const Alert = {
  alert(title: string, message?: string, buttons?: ButtonSpec[], _options?: unknown) {
    const dialog = { title, message, buttons: buttons?.length ? buttons : [{ text: 'OK' }] };
    if (show) show(dialog);
    else waiting.push(dialog);
  },
};

export function DialogHost() {
  const [queue, setQueue] = useState<Dialog[]>([]);
  useEffect(() => {
    show = (dialog) => setQueue((q) => [...q, dialog]);
    if (waiting.length) setQueue((q) => [...q, ...waiting.splice(0)]);
    return () => {
      show = null;
    };
  }, []);

  const current = queue[0];
  const close = (button?: ButtonSpec) => {
    setQueue((q) => q.slice(1));
    button?.onPress?.();
  };
  if (!current) return null;
  // Two buttons side by side, as on iOS; more go one under the other, the Cancel last.
  const ordered = [...current.buttons.filter((b) => b.style !== 'cancel'), ...current.buttons.filter((b) => b.style === 'cancel')];
  const sideBySide = ordered.length === 2;
  const shown = sideBySide ? [...ordered].reverse() : ordered;
  return (
    <Modal visible transparent animationType="fade" onRequestClose={() => close(current.buttons.find((b) => b.style === 'cancel'))}>
      <View style={styles.scrim}>
        <View style={styles.box} accessibilityRole="alert">
          <View style={styles.texts}>
            <Text style={styles.title}>{current.title}</Text>
            {current.message ? <Text style={styles.message}>{current.message}</Text> : null}
          </View>
          <View style={[styles.buttons, sideBySide && styles.row]}>
            {shown.map((button, i) => (
              <Pressable
                key={`${button.text}-${i}`}
                onPress={() => close(button)}
                accessibilityRole="button"
                style={({ pressed }) => [styles.button, sideBySide && i > 0 && styles.leftLine, pressed && styles.pressed]}>
                <Text
                  style={[
                    styles.buttonText,
                    button.style === 'destructive' && { color: colors.danger },
                    button.style === 'cancel' || (!sideBySide && i === shown.length - 1) ? null : styles.strong,
                  ]}>
                  {button.text}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)', alignItems: 'center', justifyContent: 'center', padding: spacing.xxl },
  box: { width: 290, maxWidth: '100%', backgroundColor: colors.surface, borderRadius: radius.lg, overflow: 'hidden' },
  texts: { padding: spacing.xl, paddingBottom: spacing.lg, gap: 4 },
  title: { ...fonts.headline, color: colors.text, textAlign: 'center' },
  message: { ...fonts.footnote, color: colors.textSecondary, textAlign: 'center' },
  buttons: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.separator },
  row: { flexDirection: 'row' },
  button: { flex: 1, minHeight: 46, alignItems: 'center', justifyContent: 'center', borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.separator, marginTop: -StyleSheet.hairlineWidth },
  leftLine: { borderLeftWidth: StyleSheet.hairlineWidth, borderLeftColor: colors.separator },
  pressed: { backgroundColor: colors.fill },
  buttonText: { ...fonts.body, color: colors.accent },
  strong: { fontFamily: fonts.headline.fontFamily },
});
