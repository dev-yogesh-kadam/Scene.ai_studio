import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Animated, { FadeOutUp, FadeIn } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Icon, type IconName } from './Icon';
import { colors, fonts } from '@/theme';

type Toast = { id: number; text: string; icon: IconName; tone: string };
type Show = (text: string, options?: { icon?: IconName; tone?: 'success' | 'danger' | 'info' }) => void;

const ToastContext = createContext<Show>(() => undefined);

const tones = { success: colors.success, danger: colors.danger, info: colors.accent };

/** A small pill that drops in from the top for a moment ("Saved to your gallery"), like iOS's status HUDs. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const insets = useSafeAreaInsets();
  const [toast, setToast] = useState<Toast | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const count = useRef(0);

  const show = useCallback<Show>((text, options = {}) => {
    if (timer.current) clearTimeout(timer.current);
    const tone = options.tone ?? 'success';
    setToast({ id: ++count.current, text, icon: options.icon ?? (tone === 'danger' ? 'alert-circle' : 'checkmark-circle'), tone: tones[tone] });
    timer.current = setTimeout(() => setToast(null), 2000);
  }, []);

  const value = useMemo(() => show, [show]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <View pointerEvents="none" style={[styles.layer, { top: insets.top + 8 }]} accessibilityLiveRegion="polite">
        {toast ? (
          <Animated.View key={toast.id} entering={FadeIn.duration(200)} exiting={FadeOutUp.duration(200)} style={styles.pill}>
            <Icon name={toast.icon} size={20} color={toast.tone} />
            <Text style={styles.text} numberOfLines={2}>
              {toast.text}
            </Text>
          </Animated.View>
        ) : null}
      </View>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}

const styles = StyleSheet.create({
  layer: { position: 'absolute', left: 0, right: 0, alignItems: 'center' },
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    maxWidth: '86%',
    paddingHorizontal: 18,
    paddingVertical: 12,
    borderRadius: 999,
    backgroundColor: colors.toast,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.separator,
    shadowColor: '#000',
    shadowOpacity: 0.35,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 8 },
    elevation: 12,
  },
  text: { ...fonts.subheadStrong, color: colors.text, flexShrink: 1 },
});
