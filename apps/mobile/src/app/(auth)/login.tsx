import { Image } from 'expo-image';
import * as Haptics from '@/lib/haptics';
import { useRef, useState, type ComponentRef } from 'react';
import { KeyboardAvoidingView, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import Animated, { FadeIn, LinearTransition } from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';

import { needsCode } from '@scene/shared/api/auth';
import { Button } from '@/components/Button';
import { Icon } from '@/components/Icon';
import { Tap } from '@/components/Tap';
import { useSession } from '@/hooks/useSession';
import { colors, fonts, radius, spacing } from '@/theme';

export default function LoginScreen() {
  const { signIn } = useSession();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [askCode, setAskCode] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const passwordField = useRef<ComponentRef<typeof TextInput>>(null);

  const ready = email.trim() !== '' && password !== '' && (!askCode || code.trim().length >= 6);

  async function submit() {
    if (!ready || busy) return;
    setBusy(true);
    setError('');
    try {
      await signIn(email.trim(), password, askCode ? code.trim() : undefined);
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      // The layout's guard swaps to the tabs once signed in.
    } catch (failure) {
      if (needsCode(failure)) {
        // The first answer only says a code is needed; after that it's a wrong code.
        if (askCode) setError((failure as Error).message);
        setAskCode(true);
        setCode('');
      } else {
        setError(failure instanceof Error ? failure.message : 'Could not sign in.');
      }
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <SafeAreaView style={styles.page}>
      <KeyboardAvoidingView behavior="height" style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={styles.center} keyboardShouldPersistTaps="handled">
          <Animated.View entering={FadeIn.duration(600)} style={styles.brand}>
            <View style={styles.logoGlow}>
              <Image
                source={require('@/assets/images/logo.png')}
                style={styles.logo}
                accessibilityLabel="Scene.ai logo"
              />
            </View>
            <Text style={styles.title}>Scene.ai</Text>
            <Text style={styles.subtitle}>Your studio, in your pocket</Text>
          </Animated.View>

          <Animated.View entering={FadeIn.duration(500)} layout={LinearTransition.duration(200)} style={styles.form}>
            <View style={styles.fields}>
              <TextInput
                style={styles.input}
                placeholder="Email"
                placeholderTextColor={colors.textMuted}
                autoCapitalize="none"
                autoComplete="email"
                keyboardType="email-address"
                returnKeyType="next"
                value={email}
                onChangeText={setEmail}
                onSubmitEditing={() => passwordField.current?.focus()}
                editable={!askCode}
              />
              <View style={styles.separator} />
              <TextInput
                ref={passwordField}
                style={styles.input}
                placeholder="Password"
                placeholderTextColor={colors.textMuted}
                secureTextEntry
                autoComplete="current-password"
                returnKeyType="go"
                value={password}
                onChangeText={setPassword}
                editable={!askCode}
                onSubmitEditing={submit}
              />
            </View>

            {askCode ? (
              <Animated.View entering={FadeIn.duration(200)} style={styles.codeBox}>
                <View style={styles.codeHeader}>
                  <Icon name="shield-checkmark" size={18} color={colors.accent} />
                  <Text style={styles.hint}>
                    Enter the 6-digit code from your authenticator app, or a recovery code.
                  </Text>
                </View>
                <TextInput
                  style={[styles.fields, styles.input, styles.code]}
                  placeholder="000000"
                  placeholderTextColor={colors.textMuted}
                  autoFocus
                  autoCapitalize="none"
                  autoComplete="one-time-code"
                  keyboardType="number-pad"
                  value={code}
                  onChangeText={setCode}
                  onSubmitEditing={submit}
                />
              </Animated.View>
            ) : null}

            {error ? (
              <Animated.View entering={FadeIn.duration(200)} style={styles.errorRow}>
                <Icon name="alert-circle" size={16} color={colors.danger} />
                <Text style={styles.error}>{error}</Text>
              </Animated.View>
            ) : null}

            <Button label={askCode ? 'Verify' : 'Sign In'} onPress={submit} busy={busy} disabled={!ready} />

            {askCode ? (
              <Tap
                onPress={() => {
                  setAskCode(false);
                  setCode('');
                  setError('');
                }}
                style={styles.linkBox}
              >
                <Text style={styles.link}>Use a different account</Text>
              </Tap>
            ) : null}
          </Animated.View>
        </ScrollView>
        <Text style={styles.server} onPress={() => window.location.assign('/?desktop=1')} accessibilityRole="link">
          Open the full studio
        </Text>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.background },
  center: {
    flexGrow: 1,
    justifyContent: 'center',
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.xxl,
    gap: 40,
  },
  brand: { alignItems: 'center' },
  logoGlow: {
    borderRadius: 28,
    shadowColor: colors.accent,
    shadowOpacity: 0.6,
    shadowRadius: 30,
    shadowOffset: { width: 0, height: 10 },
    elevation: 16,
    marginBottom: spacing.xl,
  },
  logo: { width: 96, height: 96 },
  title: { ...fonts.largeTitle, color: colors.text },
  subtitle: { ...fonts.callout, color: colors.textSecondary, marginTop: 4 },
  form: { gap: spacing.lg },
  fields: { backgroundColor: colors.surface, borderRadius: radius.md, overflow: 'hidden' },
  input: { ...fonts.body, color: colors.text, paddingHorizontal: spacing.lg, height: 52 },
  separator: { height: StyleSheet.hairlineWidth, backgroundColor: colors.separator, marginLeft: spacing.lg },
  codeBox: { gap: spacing.md },
  codeHeader: { flexDirection: 'row', gap: spacing.sm, alignItems: 'flex-start', paddingHorizontal: 4 },
  code: { fontSize: 26, letterSpacing: 10, textAlign: 'center', height: 60 },
  hint: { ...fonts.footnote, color: colors.textSecondary, flex: 1 },
  errorRow: { flexDirection: 'row', gap: 6, alignItems: 'flex-start', paddingHorizontal: 4 },
  error: { ...fonts.footnote, color: colors.danger, flex: 1 },
  linkBox: { alignSelf: 'center', padding: spacing.sm },
  link: { ...fonts.subhead, color: colors.accent },
  server: { ...fonts.footnote, color: colors.accent, textAlign: 'center', paddingBottom: spacing.lg },
});
