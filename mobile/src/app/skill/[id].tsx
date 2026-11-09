import { useQuery } from '@tanstack/react-query';
import * as Clipboard from 'expo-clipboard';
import { router, useLocalSearchParams } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';

import { listSkills } from '@/api/skills';
import { Button } from '@/components/Button';
import { Chip } from '@/components/Chip';
import { Icon } from '@/components/Icon';
import { Markdown } from '@/components/Markdown';
import { Skeleton } from '@/components/Skeleton';
import { LargeTitle, TitledScreen, useScrollY } from '@/components/TitledScreen';
import { useToast } from '@/components/Toast';
import { skillLook } from '@/lib/skills';
import { colors, fonts, lines, radius, spacing } from '@/theme';

export default function SkillScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const toast = useToast();
  const { scrollY, onScroll } = useScrollY();
  const skills = useQuery({ queryKey: ['skills'], queryFn: listSkills, staleTime: 10 * 60_000 });
  const skill = skills.data?.skills.find((s) => s.id === id);
  const look = skill ? skillLook(skill) : null;
  const next = (skill?.next ?? []).map((n) => skills.data?.skills.find((s) => s.id === n)).filter((s) => !!s);

  return (
    <TitledScreen title={skill?.title ?? 'Skill'} back scrollY={scrollY}>
      <Animated.ScrollView onScroll={onScroll} scrollEventThrottle={16} contentContainerStyle={styles.content}>
        <LargeTitle title={skill ? skill.title : ' '} subtitle={skill ? `${skill.craft ? 'Craft skill' : 'Recipe'} · version ${skill.version}` : undefined} scrollY={scrollY} />
        {!skill ? (
          <View style={[styles.pad, { gap: spacing.md }]}>
            <Skeleton style={{ height: 120, borderRadius: radius.lg }} />
            <Skeleton style={{ height: 300, borderRadius: radius.lg }} />
          </View>
        ) : (
          <Animated.View entering={FadeIn.duration(200)} style={[styles.pad, { gap: spacing.xl }]}>
            <View style={styles.card}>
              <View style={[styles.icon, { backgroundColor: look!.color }]}>
                <Icon name={look!.icon} size={28} color="#fff" />
              </View>
              <Text style={styles.desc}>{skill.desc}</Text>
              <View style={styles.use}>
                <Text style={styles.useText}>
                  The agent uses it by itself when a message fits. To ask for it, start a message in the studio with{' '}
                  <Text style={styles.command}>/{skill.id}</Text>
                </Text>
                <Button
                  small
                  variant="tinted"
                  icon="copy-outline"
                  label={`Copy /${skill.id}`}
                  onPress={async () => {
                    await Clipboard.setStringAsync(`/${skill.id} `);
                    toast('Command Copied', { icon: 'copy' });
                  }}
                />
              </View>
            </View>

            {next.length ? (
              <View style={{ gap: spacing.sm }}>
                <Text style={styles.label}>WORKS WELL WITH</Text>
                <View style={styles.chips}>
                  {next.map((s) => (
                    <Chip key={s!.id} label={s!.title} onPress={() => router.push({ pathname: '/skill/[id]', params: { id: s!.id } })} />
                  ))}
                </View>
              </View>
            ) : null}

            <View style={{ gap: spacing.sm }}>
              <Text style={styles.label}>THE RECIPE</Text>
              <View style={styles.recipe}>
                <Markdown text={skill.text} />
              </View>
            </View>
          </Animated.View>
        )}
      </Animated.ScrollView>
    </TitledScreen>
  );
}

const styles = StyleSheet.create({
  content: { paddingBottom: spacing.xxl * 2 },
  pad: { paddingHorizontal: spacing.lg },
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.xl, gap: spacing.lg },
  icon: { width: 56, height: 56, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  desc: { ...fonts.body, color: colors.text, lineHeight: lines(24) },
  use: { gap: spacing.md, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.separator, paddingTop: spacing.lg, alignItems: 'flex-start' },
  useText: { ...fonts.footnote, color: colors.textSecondary },
  command: { fontFamily: 'monospace', color: colors.accent },
  label: { ...fonts.footnoteStrong, color: colors.textSecondary, letterSpacing: 0.5 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  recipe: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.xl },
});
