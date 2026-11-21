import { useQuery } from '@tanstack/react-query';
import { LinearGradient } from 'expo-linear-gradient';
import { useState } from 'react';
import { RefreshControl, StyleSheet, Text, TextInput, View } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';

import { credits as creditsOf, requestCredits } from '@scene/shared/api/studio';
import { Button } from '@/components/Button';
import { ChipRow } from '@/components/Chip';
import { Group, Row } from '@/components/Group';
import { Segmented } from '@/components/Segmented';
import { Sheet } from '@/components/Sheet';
import { useToast } from '@/components/Toast';
import { LargeTitle, TitledScreen, useBarInset, useScrollY } from '@/components/TitledScreen';
import { WhatsNew } from '@/components/WhatsNew';
import { useSession } from '@/hooks/useSession';
import { creditReason, initials, timeAgo } from '@scene/shared/format';
import { releases, version, type Release } from '@/lib/whatsNew';
import { choose, chosen, type Choice } from '@/theme/appearance';
import { colors, fonts, gradient, radius, spacing } from '@/theme';
import { Alert } from '@/lib/dialog';

export default function AccountScreen() {
  const { user, signOut } = useSession();
  const { scrollY, onScroll } = useScrollY();
  const barInset = useBarInset();
  const credits = useQuery({ queryKey: ['credits'], queryFn: creditsOf });
  const [leaving, setLeaving] = useState(false);
  const toast = useToast();
  const [appearance, setAppearance] = useState<Choice>(chosen());
  const [asking, setAsking] = useState(false);
  const [news, setNews] = useState<Release | null>(null);
  const [amount, setAmount] = useState(500);
  const [note, setNote] = useState('');
  const [sending, setSending] = useState(false);

  async function ask() {
    setSending(true);
    try {
      await requestCredits(amount, note);
      setAsking(false);
      setNote('');
      toast('Sent to the admins', { icon: 'paper-plane' });
    } catch (e) {
      Alert.alert("Couldn't Send It", e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  }
  const [showAll, setShowAll] = useState(false);

  const balance = credits.data?.balance ?? user?.credits ?? 0;
  const events = credits.data?.events ?? [];
  const spent = events.filter((e) => e.amount < 0 && e.created > Date.now() / 1000 - 30 * 86400).reduce((sum, e) => sum - e.amount, 0);

  function confirmSignOut() {
    Alert.alert('Sign Out?', 'You sign out of the studio on this browser too.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Sign Out',
        style: 'destructive',
        onPress: async () => {
          setLeaving(true);
          await signOut();
        },
      },
    ]);
  }

  return (
    <TitledScreen title="Account" back scrollY={scrollY}>
      <Animated.ScrollView
        onScroll={onScroll}
        scrollEventThrottle={16}
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={credits.isRefetching}
            onRefresh={() => {
              void credits.refetch();
            }}
            progressViewOffset={barInset}
            tintColor={colors.textSecondary}
            colors={[colors.accent]}
            progressBackgroundColor={colors.surface}
          />
        }>
        <LargeTitle title="Account" scrollY={scrollY} />

        <View style={styles.body}>
          {user ? (
            <Animated.View entering={FadeIn.duration(200)} style={styles.profile}>
              <LinearGradient colors={gradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.avatar}>
                <Text style={styles.avatarText}>{initials(user.name) || '?'}</Text>
              </LinearGradient>
              <View style={{ flex: 1 }}>
                <Text style={styles.name}>{user.name}</Text>
                <Text style={styles.email}>{user.email}</Text>
              </View>
              {user.role !== 'user' ? (
                <View style={styles.role}>
                  <Text style={styles.roleText}>{user.role}</Text>
                </View>
              ) : null}
            </Animated.View>
          ) : null}

          <Animated.View entering={FadeIn.duration(200)} style={styles.credits}>
            <LinearGradient colors={[colors.heroFrom, colors.heroTo]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={StyleSheet.absoluteFill} />
            <Text style={styles.creditsLabel}>Credits</Text>
            <Text style={styles.balance}>{balance.toLocaleString()}</Text>
            <Text style={styles.creditsNote}>{spent ? `${spent.toLocaleString()} spent in the last 30 days` : 'Ask an admin when you need more'}</Text>
            <View style={{ alignItems: 'flex-start', marginTop: spacing.md }}>
              <Button small variant="tinted" icon="add-circle" label="Ask for More" onPress={() => setAsking(true)} />
            </View>
          </Animated.View>

          {events.length ? (
            <Group title="Activity">
              {(showAll ? events : events.slice(0, 4)).map((event, index) => (
                <Row
                  key={`${event.created}-${index}`}
                  title={event.job_name ?? (event.note || creditReason(event.reason))}
                  subtitle={`${creditReason(event.reason)} · ${timeAgo(event.created)}`}
                  right={
                    <Text style={[styles.amount, { color: event.amount > 0 ? colors.success : colors.textSecondary }]}>
                      {event.amount > 0 ? '+' : ''}
                      {event.amount.toLocaleString()}
                    </Text>
                  }
                />
              ))}
              {events.length > 4 ? (
                <Row title={showAll ? 'Show Less' : `Show All ${events.length}`} onPress={() => setShowAll(!showAll)} right={<View />} />
              ) : null}
            </Group>
          ) : null}

          <Group title="Appearance" footer={appearance === chosen() ? undefined : 'Shows the next time you open Scene.ai.'}>
            <View style={styles.appearance}>
              <Segmented
                options={[
                  { value: 'system', label: 'Automatic' },
                  { value: 'dark', label: 'Dark' },
                  { value: 'light', label: 'Light' },
                ]}
                value={appearance}
                onChange={(next) => {
                  choose(next);
                  setAppearance(next);
                  toast('Shows the next time you open Scene.ai', { icon: 'contrast', tone: 'info' });
                }}
              />
            </View>
          </Group>

          <Group title="Studio">
            <Row icon="desktop" tint="#5E5CE6" title="Open the Full Studio" subtitle="The desktop studio, on this phone" chevron onPress={() => window.location.assign('/?desktop=1')} />
            <Row icon="information-circle" tint="#8E8E93" title="Version" detail={version} />
            <Row icon="sparkles" tint={colors.accent} title="What's New" chevron onPress={() => setNews(releases[0])} />
          </Group>

          <Group>
            <Row title={leaving ? 'Signing Out…' : 'Sign Out'} destructive onPress={leaving ? undefined : confirmSignOut} />
          </Group>
        </View>
      </Animated.ScrollView>

      <WhatsNew release={news} onClose={() => setNews(null)} />

      <Sheet open={asking} onClose={() => setAsking(false)} title="Ask for Credits">
        <Text style={styles.askText}>The admins see your request in the admin console, and on their phones if they have the app.</Text>
        <ChipRow
          padded={false}
          options={[100, 500, 1000, 5000].map((n) => ({ value: n, label: n.toLocaleString() }))}
          value={amount}
          onChange={setAmount}
        />
        <TextInput
          style={styles.askInput}
          placeholder="What it's for (optional)"
          placeholderTextColor={colors.textMuted}
          value={note}
          onChangeText={setNote}
          maxLength={300}
          multiline
        />
        <Button label={`Ask for ${amount.toLocaleString()} Credits`} icon="paper-plane" onPress={() => void ask()} busy={sending} />
      </Sheet>
    </TitledScreen>
  );
}

const styles = StyleSheet.create({
  content: { paddingBottom: spacing.xxl * 2 },
  body: { paddingHorizontal: spacing.lg, gap: spacing.xl },
  profile: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.lg },
  avatar: { width: 60, height: 60, borderRadius: 30, alignItems: 'center', justifyContent: 'center' },
  avatarText: { ...fonts.title2, color: colors.onBrand },
  name: { ...fonts.title3, color: colors.text },
  email: { ...fonts.subhead, color: colors.textSecondary },
  role: { backgroundColor: colors.accentSoft, paddingHorizontal: spacing.sm, paddingVertical: 3, borderRadius: radius.pill },
  roleText: { ...fonts.caption2, color: colors.accent, textTransform: 'capitalize' },
  credits: { borderRadius: radius.lg, padding: spacing.xl, overflow: 'hidden', gap: 2 },
  creditsLabel: { ...fonts.footnoteStrong, color: colors.textSecondary, textTransform: 'uppercase', letterSpacing: 0.4 },
  balance: { ...fonts.hero, color: colors.text },
  creditsNote: { ...fonts.footnote, color: colors.textSecondary },
  amount: { ...fonts.calloutStrong },
  appearance: { padding: spacing.md },
  askText: { ...fonts.subhead, color: colors.textSecondary },
  askInput: { ...fonts.body, color: colors.text, backgroundColor: colors.surfaceRaised, borderRadius: radius.md, padding: spacing.md, minHeight: 80, textAlignVertical: 'top' },
});
