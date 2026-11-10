import { useEffect, useState, type ReactNode } from 'react';
import { KeyboardAvoidingView, Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, { Easing, runOnJS, useAnimatedStyle, useSharedValue, withTiming } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors, fonts, radius, spacing } from '@/theme';

const ease = Easing.out(Easing.cubic);

/** An iOS-style sheet: slides up over a dimmed screen; drag it down, tap outside or press Back to close. */
export function Sheet({ open, onClose, title, children }: { open: boolean; onClose: () => void; title?: string; children: ReactNode }) {
  const insets = useSafeAreaInsets();
  const [shown, setShown] = useState(open);
  const offset = useSharedValue(800);
  const dim = useSharedValue(0);

  useEffect(() => {
    if (open) {
      setShown(true);
      offset.value = withTiming(0, { duration: 300, easing: ease });
      dim.value = withTiming(1, { duration: 250 });
    } else if (shown) {
      dim.value = withTiming(0, { duration: 200 });
      offset.value = withTiming(800, { duration: 220 }, (done) => {
        if (done) runOnJS(setShown)(false);
      });
    }
  }, [open, shown, offset, dim]);

  const drag = Gesture.Pan()
    .activeOffsetY(8)
    .onUpdate((event) => {
      offset.value = Math.max(0, event.translationY);
    })
    .onEnd((event) => {
      if (event.translationY > 120 || event.velocityY > 900) runOnJS(onClose)();
      else offset.value = withTiming(0, { duration: 200, easing: ease });
    });

  const sheetStyle = useAnimatedStyle(() => ({ transform: [{ translateY: offset.value }] }));
  const scrimStyle = useAnimatedStyle(() => ({ opacity: dim.value }));

  return (
    <Modal visible={shown} transparent animationType="none" onRequestClose={onClose} statusBarTranslucent navigationBarTranslucent>
      <KeyboardAvoidingView behavior="padding" style={styles.fill}>
        <Animated.View style={[styles.scrim, scrimStyle]}>
          <Pressable style={styles.fill} onPress={onClose} accessibilityLabel="Close" />
        </Animated.View>
        <Animated.View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.lg }, sheetStyle]}>
          <GestureDetector gesture={drag}>
            <View style={styles.top}>
              <View style={styles.grabber} />
              {title ? <Text style={styles.title}>{title}</Text> : null}
            </View>
          </GestureDetector>
          <ScrollView bounces={false} keyboardShouldPersistTaps="handled" contentContainerStyle={styles.content}>
            {children}
          </ScrollView>
        </Animated.View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, justifyContent: 'flex-end' },
  scrim: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.55)' },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    paddingHorizontal: spacing.lg,
    maxHeight: '88%',
  },
  top: { paddingTop: 6, paddingBottom: spacing.md, alignItems: 'center' },
  grabber: { width: 36, height: 5, borderRadius: 3, backgroundColor: 'rgba(235,235,245,0.3)', marginBottom: spacing.md },
  title: { ...fonts.headline, color: colors.text },
  content: { gap: spacing.lg, paddingBottom: spacing.sm },
});
