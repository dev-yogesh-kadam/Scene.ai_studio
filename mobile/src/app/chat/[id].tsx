import { useQuery, useQueryClient } from '@tanstack/react-query';
import { LinearGradient } from 'expo-linear-gradient';
import * as Haptics from '@/lib/haptics';
import { router, useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, FlatList, KeyboardAvoidingView, StyleSheet, Text, TextInput, View } from 'react-native';
import Animated, { FadeIn, useAnimatedStyle, useSharedValue, withRepeat, withSequence, withTiming } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { getModule } from '@/api/projects';
import { listJobs } from '@/api/runs';
import { Button, IconButton } from '@/components/Button';
import { Icon, kindIcons, type IconName } from '@/components/Icon';
import { Markdown } from '@/components/Markdown';
import { Sheet } from '@/components/Sheet';
import { Group, Row } from '@/components/Group';
import { Tap } from '@/components/Tap';
import { Thumb } from '@/components/Thumb';
import { useToast } from '@/components/Toast';
import { useScreenFocused } from '@/hooks/useScreenFocused';
import { useSession } from '@/hooks/useSession';
import {
  approve,
  ask,
  collectResults,
  GO,
  loadConversation,
  loadTabs,
  newTab,
  saveConversation,
  saveIndex,
  type Conversation,
  type Run,
  type Step,
  type Tab,
  type TabIndex,
} from '@/lib/agent';
import { credits, timeAgo } from '@/lib/format';
import { colors, fonts, gradient, radius, spacing } from '@/theme';
import type { Job } from '@/types/api';
import { Alert } from '@/lib/dialog';

const SUGGESTIONS = ['Plan a 30-second film from one line', 'Make three shots of a fox in the snow', 'Write a short script for a product ad', 'What can you do?'];

export default function ChatScreen() {
  const { id, tab: askedTab } = useLocalSearchParams<{ id: string; tab?: string }>();
  const project = Number(id);
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const queryClient = useQueryClient();
  const focused = useScreenFocused();
  const { user } = useSession();
  const module = useQuery({ queryKey: ['module', project], queryFn: () => getModule(project) });

  const [index, setIndex] = useState<TabIndex | null>(null);
  const [tab, setTab] = useState<Tab | null>(null);
  const [convo, setConvo] = useState<Conversation | null>(null);
  const [, setVersion] = useState(0);
  const bump = useCallback(() => setVersion((v) => v + 1), []);
  const [text, setText] = useState('');
  const [pending, setPending] = useState<{ text: string; status: string } | null>(null);
  const [working, setWorking] = useState(false);
  const [tabsOpen, setTabsOpen] = useState(false);
  const [error, setError] = useState('');
  const controller = useRef<AbortController | null>(null);
  const halted = useRef(false);
  const list = useRef<FlatList<Run>>(null);

  // The module's conversations: the tab asked for (from a waiting plan), else the one open last.
  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const found = await loadTabs(project);
        if (!live) return;
        const chosen = found.tabs.find((t) => t.id === askedTab) ?? found.tabs.find((t) => t.id === found.active) ?? found.tabs[0];
        setIndex(found);
        setTab(chosen);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      live = false;
    };
  }, [project, askedTab]);

  useEffect(() => {
    if (!tab) return;
    let live = true;
    setConvo(null);
    loadConversation(project, tab.id)
      .then((found) => live && setConvo(found))
      .catch((e) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [project, tab]);

  const save = useCallback(() => {
    if (!convo || !tab) return;
    void saveConversation(project, tab.id, convo);
    bump();
  }, [convo, tab, project, bump]);

  // Steps it queued: their jobs, to show how far each is and what it made.
  const queued = (convo?.runs ?? []).some((r) => r.steps.some((s) => s.job && !s.made));
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: listJobs, refetchInterval: focused && queued ? 3000 : false });
  useEffect(() => {
    if (convo && jobs.data && collectResults(convo, jobs.data.jobs)) save();
  }, [jobs.data, convo, save]);
  const jobOf = (step: Step): Job | undefined => (step.job ? jobs.data?.jobs.find((j) => j.id === step.job) : undefined);

  async function send(typed?: string) {
    const message = (typed ?? text).trim();
    if (!message || !convo || !tab || pending || working) return;
    const waiting = convo.runs[convo.runs.length - 1];
    // "approve", "go ahead"… under a plan that waits is the Approve button: asking again would only answer in words.
    if (!typed && waiting?.state === 'proposed' && GO.test(message)) {
      setText('');
      return runPlan(waiting);
    }
    setText('');
    setError('');
    setPending({ text: message, status: 'Thinking' });
    void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    controller.current = new AbortController();
    try {
      await ask(project, tab, convo, message, (event) => {
        if (event.type === 'status' && typeof event.text === 'string') setPending({ text: message, status: event.text });
      }, controller.current.signal);
      void saveConversation(project, tab.id, convo);
      if (index) {
        const next = { ...index, active: tab.id, tabs: index.tabs.map((t) => (t.id === tab.id ? { ...t, updated: Date.now() } : t)) };
        setIndex(next);
        void saveIndex(project, next);
      }
      void queryClient.invalidateQueries({ queryKey: ['credits'] });
      void queryClient.invalidateQueries({ queryKey: ['waiting'] });
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') setText(message);
      else {
        convo.runs.push({ instruction: message, reply: e instanceof Error ? e.message : String(e), error: true, steps: [], total: 0, state: 'answered', at: Date.now() });
        void saveConversation(project, tab.id, convo);
      }
    } finally {
      setPending(null);
      controller.current = null;
      bump();
    }
  }

  async function runPlan(run: Run) {
    if (!convo || working) return;
    const balance = queryClient.getQueryData<{ balance: number }>(['credits'])?.balance ?? user?.credits;
    if (balance != null && run.total > balance) {
      return Alert.alert('Not Enough Credits', `This plan needs ${credits(run.total)} and you have ${credits(balance)}.`);
    }
    setWorking(true);
    halted.current = false;
    void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    await approve(project, run, save, () => halted.current);
    setWorking(false);
    save();
    const failed = run.steps.find((s) => s.error);
    if (failed) toast(`"${failed.name}" wasn't made`, { tone: 'danger' });
    else toast('Plan started', { icon: 'sparkles' });
    void queryClient.invalidateQueries({ queryKey: ['jobs'] });
    void queryClient.invalidateQueries({ queryKey: ['credits'] });
    void queryClient.invalidateQueries({ queryKey: ['waiting'] });
  }

  function dismiss(run: Run) {
    run.state = 'dismissed';
    save();
    void queryClient.invalidateQueries({ queryKey: ['waiting'] });
  }

  async function startTab() {
    if (!index) return;
    const made = await newTab(project, index);
    setIndex(made.index);
    setTab(made.tab);
    setTabsOpen(false);
  }

  const runs = convo?.runs ?? [];
  useEffect(() => {
    const timer = setTimeout(() => list.current?.scrollToEnd({ animated: true }), 120);
    return () => clearTimeout(timer);
  }, [runs.length, pending]);

  const last = runs[runs.length - 1];
  return (
    <View style={styles.page}>
      <View style={[styles.header, { paddingTop: insets.top + 6 }]}>
        <IconButton icon="chevron-back" label="Back" onPress={() => router.back()} />
        <Tap onPress={() => setTabsOpen(true)} scaleTo={0.96} style={styles.titleBox}>
          <View style={styles.titleRow}>
            <Text style={styles.title} numberOfLines={1}>
              {tab?.name ?? 'Agent'}
            </Text>
            <Icon name="chevron-down" size={14} color={colors.textSecondary} />
          </View>
          <Text style={styles.subtitle} numberOfLines={1}>
            {module.data ? `${module.data.module.project.name} · ${module.data.module.name}` : ' '}
          </Text>
        </Tap>
        <IconButton icon="create-outline" label="New conversation" onPress={() => void startTab()} />
      </View>

      <KeyboardAvoidingView behavior="padding" style={{ flex: 1 }} keyboardVerticalOffset={0}>
        {!convo ? (
          <View style={styles.center}>{error ? <Text style={styles.errorText}>{error}</Text> : <ActivityIndicator color={colors.textSecondary} />}</View>
        ) : (
          <FlatList
            ref={list}
            data={runs}
            keyExtractor={(run, i) => `${run.at}-${i}`}
            contentContainerStyle={styles.log}
            keyboardDismissMode="interactive"
            onContentSizeChange={() => list.current?.scrollToEnd({ animated: false })}
            ListEmptyComponent={
              pending ? undefined : (
                <Animated.View entering={FadeIn.duration(400)} style={styles.empty}>
                  <LinearGradient colors={gradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.emptyIcon}>
                    <Icon name="sparkles" size={30} color={colors.onBrand} />
                  </LinearGradient>
                  <Text style={styles.emptyTitle}>Ask the Agent</Text>
                  <Text style={styles.emptyText}>It plans shots, writes, keeps your cast the same, and shows the price before anything is made.</Text>
                  <View style={styles.suggestions}>
                    {SUGGESTIONS.map((s) => (
                      <Tap key={s} onPress={() => setText(s)} haptic="selection" scaleTo={0.96} style={styles.suggestion}>
                        <Text style={styles.suggestionText}>{s}</Text>
                      </Tap>
                    ))}
                  </View>
                </Animated.View>
              )
            }
            renderItem={({ item: run }) => (
              <Turn
                run={run}
                latest={run === last}
                working={working && run === last}
                jobOf={jobOf}
                onApprove={() => void runPlan(run)}
                onDismiss={() => dismiss(run)}
                onStop={() => (halted.current = true)}
                onAnswer={(answer) => {
                  if (run.question) run.question.answer = answer;
                  save();
                  void send(answer);
                }}
                onAnswers={(picks) => {
                  run.picks = picks;
                  run.questionsSent = true;
                  save();
                  void send('My answers:\n' + (run.questions ?? []).map((q, i) => `${i + 1}. ${q.text} — ${picks[i]}`).join('\n'));
                }}
                onPicks={(picks) => {
                  run.picks = picks;
                  bump();
                }}
              />
            )}
            ListFooterComponent={
              pending ? (
                <View>
                  <Bubble text={pending.text} />
                  <Thinking status={pending.status} onStop={() => controller.current?.abort()} />
                </View>
              ) : undefined
            }
          />
        )}

        <View style={[styles.composer, { paddingBottom: Math.max(insets.bottom, spacing.sm) }]}>
          <View style={styles.inputBox}>
            <TextInput
              style={styles.input}
              placeholder={last?.state === 'proposed' ? 'Say "go ahead", or ask for a change…' : 'Message the agent…'}
              placeholderTextColor={colors.textMuted}
              value={text}
              onChangeText={setText}
              multiline
              maxLength={2000}
              editable={!pending}
            />
            <Tap onPress={() => void send()} disabled={!text.trim() || !!pending || !convo} haptic="light" scaleTo={0.85}>
              <LinearGradient colors={text.trim() ? gradient : [colors.surfaceRaised, colors.surfaceRaised]} style={styles.sendButton}>
                <Icon name="arrow-up" size={20} color={text.trim() ? colors.onBrand : colors.textMuted} />
              </LinearGradient>
            </Tap>
          </View>
        </View>
      </KeyboardAvoidingView>

      <Sheet open={tabsOpen} onClose={() => setTabsOpen(false)} title="Conversations">
        <Group>
          {[...(index?.tabs ?? [])]
            .sort((a, b) => b.updated - a.updated)
            .map((t) => (
              <Row
                key={t.id}
                icon="chatbubbles"
                tint={t.id === tab?.id ? colors.accent : '#636366'}
                title={t.name}
                subtitle={`Last used ${timeAgo(t.updated / 1000)}`}
                right={t.id === tab?.id ? <Icon name="checkmark" size={18} color={colors.accent} /> : <View />}
                onPress={() => {
                  setTab(t);
                  setTabsOpen(false);
                  if (index) void saveIndex(project, { ...index, active: t.id });
                }}
              />
            ))}
        </Group>
        <Button label="New Conversation" icon="add" variant="secondary" onPress={() => void startTab()} />
      </Sheet>
    </View>
  );
}

function Bubble({ text }: { text: string }) {
  return (
    <Animated.View entering={FadeIn.duration(200)} style={styles.mine}>
      <LinearGradient colors={gradient} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.mineBubble}>
        <Text style={styles.mineText}>{text}</Text>
      </LinearGradient>
    </Animated.View>
  );
}

/** The three dots and what it is doing, while it works. */
function Thinking({ status, onStop }: { status: string; onStop: () => void }) {
  const pulse = useSharedValue(0.3);
  useEffect(() => {
    pulse.value = withRepeat(withSequence(withTiming(1, { duration: 500 }), withTiming(0.3, { duration: 500 })), -1);
  }, [pulse]);
  const dot = useAnimatedStyle(() => ({ opacity: pulse.value }));
  return (
    <Animated.View entering={FadeIn.duration(200)} style={styles.thinking}>
      <View style={styles.agentAvatar}>
        <Icon name="sparkles" size={14} color={colors.onAccent} />
      </View>
      <View style={styles.thinkingBubble}>
        <Animated.View style={[styles.dots, dot]}>
          <View style={styles.dot} />
          <View style={styles.dot} />
          <View style={styles.dot} />
        </Animated.View>
        <Text style={styles.thinkingText} numberOfLines={2}>
          {status}…
        </Text>
      </View>
      <Tap onPress={onStop} hitSlop={10} scaleTo={0.85}>
        <Icon name="stop-circle" size={26} color={colors.textSecondary} />
      </Tap>
    </Animated.View>
  );
}

type TurnProps = {
  run: Run;
  latest: boolean;
  working: boolean;
  jobOf: (step: Step) => Job | undefined;
  onApprove: () => void;
  onDismiss: () => void;
  onStop: () => void;
  onAnswer: (answer: string) => void;
  onAnswers: (picks: string[]) => void;
  onPicks: (picks: string[]) => void;
};

function Turn({ run, latest, working, jobOf, onApprove, onDismiss, onStop, onAnswer, onAnswers, onPicks }: TurnProps) {
  const [showWork, setShowWork] = useState(false);
  const activity = (run.activity ?? []).filter((a) => a.text);
  return (
    <View style={styles.turn}>
      {run.instruction && !run.auto ? <Bubble text={run.instruction} /> : null}
      <Animated.View entering={FadeIn.duration(200)} style={styles.theirs}>
        <View style={[styles.agentAvatar, run.error && { backgroundColor: colors.danger }]}>
          <Icon name={run.error ? 'alert' : 'sparkles'} size={14} color={run.error ? '#fff' : colors.onAccent} />
        </View>
        <View style={styles.theirsBody}>
          {run.reply ? (
            <View style={[styles.reply, run.error && styles.replyError]}>
              <Markdown text={run.reply} />
            </View>
          ) : null}
          {activity.length ? (
            <Tap onPress={() => setShowWork(!showWork)} scaleTo={0.98} style={styles.workToggle}>
              <Icon name={showWork ? 'chevron-down' : 'chevron-forward'} size={13} color={colors.textMuted} />
              <Text style={styles.workToggleText}>
                {showWork ? 'Hide' : 'Show'} what it did ({activity.length})
              </Text>
            </Tap>
          ) : null}
          {showWork ? (
            <View style={styles.work}>
              {activity.map((a, i) => (
                <Text key={i} style={styles.workLine}>
                  · {a.text}
                </Text>
              ))}
            </View>
          ) : null}

          {run.question ? (
            <View style={styles.question}>
              <Text style={styles.questionText}>{run.question.text}</Text>
              <View style={styles.options}>
                {run.question.options.map((option) => (
                  <Button
                    key={option}
                    small
                    variant={run.question?.answer === option ? 'primary' : 'secondary'}
                    label={option}
                    disabled={!latest || !!run.question?.answer}
                    onPress={() => onAnswer(option)}
                  />
                ))}
              </View>
            </View>
          ) : null}

          {run.questions?.length ? (
            <View style={styles.question}>
              {run.questions.map((q, i) => {
                const picks = run.picks ?? run.questions!.map((x) => x.default ?? x.options[0]);
                return (
                  <View key={i} style={{ gap: spacing.sm }}>
                    <Text style={styles.questionText}>
                      {i + 1}. {q.text}
                    </Text>
                    <View style={styles.options}>
                      {q.options.map((option) => (
                        <Button
                          key={option}
                          small
                          variant={picks[i] === option ? 'tinted' : 'secondary'}
                          label={option}
                          disabled={!latest || run.questionsSent}
                          onPress={() => onPicks(picks.map((p, n) => (n === i ? option : p)))}
                        />
                      ))}
                    </View>
                  </View>
                );
              })}
              {latest && !run.questionsSent ? (
                <Button small label="Send Answers" onPress={() => onAnswers(run.picks ?? run.questions!.map((x) => x.default ?? x.options[0]))} />
              ) : null}
            </View>
          ) : null}

          {run.steps.length ? <PlanCard run={run} latest={latest} working={working} jobOf={jobOf} onApprove={onApprove} onDismiss={onDismiss} onStop={onStop} /> : null}
        </View>
      </Animated.View>
    </View>
  );
}

const stepIcons: Record<string, IconName> = { ...kindIcons, edit: 'cut', motion: 'text', sound: 'volume-high', assemble: 'film' };

function PlanCard({ run, latest, working, jobOf, onApprove, onDismiss, onStop }: Omit<TurnProps, 'onAnswer' | 'onAnswers' | 'onPicks'>) {
  const queryClient = useQueryClient();
  const steps = run.steps.filter((s) => !s.skipped);
  const proposed = run.state === 'proposed';
  const open = (id: number) => router.push({ pathname: '/watch/[id]', params: { id: String(id) } });
  return (
    <View style={styles.plan}>
      <View style={styles.planHeader}>
        <Text style={styles.planTitle}>
          Plan · {steps.length} {steps.length === 1 ? 'step' : 'steps'}
        </Text>
        <Text style={styles.planTotal}>{credits(run.total)}</Text>
      </View>
      {steps.map((step, i) => {
        const job = jobOf(step);
        const kind = step.assemble ? 'assemble' : step.motion ? 'motion' : step.sound ? 'sound' : step.edit ? 'edit' : step.kind ?? 'image';
        const state = step.error
          ? { text: step.error, color: colors.danger, icon: 'alert-circle' as IconName }
          : step.made || job?.status === 'done'
            ? { text: 'Ready', color: colors.success, icon: 'checkmark-circle' as IconName }
            : job?.status === 'running'
              ? { text: 'Rendering', color: colors.accent, icon: 'sync' as IconName }
              : job?.status === 'failed'
                ? { text: job.reason ?? 'Failed', color: colors.danger, icon: 'alert-circle' as IconName }
                : step.job
                  ? { text: 'Queued', color: colors.warning, icon: 'time' as IconName }
                  : null;
        const made = step.made ?? job?.items[0]?.id;
        return (
          <Tap
            key={i}
            disabled={!made}
            scaleTo={made ? 0.98 : 1}
            onPress={() => {
              if (!made) return;
              void queryClient.invalidateQueries({ queryKey: ['item', made] });
              open(made);
            }}
            style={[styles.step, i > 0 && styles.stepLine]}>
            {made ? (
              <Thumb id={made} kind={job?.items[0]?.kind ?? step.kind ?? 'image'} style={styles.stepThumb} iconSize={18} />
            ) : (
              <View style={styles.stepIcon}>
                <Icon name={stepIcons[kind] ?? 'sparkles'} size={18} color={colors.accent} />
              </View>
            )}
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={styles.stepName} numberOfLines={1}>
                {step.name}
              </Text>
              {step.prompt ? (
                <Text style={styles.stepPrompt} numberOfLines={2}>
                  {step.prompt}
                </Text>
              ) : step.workflow_title ? (
                <Text style={styles.stepPrompt} numberOfLines={1}>
                  {step.workflow_title}
                </Text>
              ) : null}
              {state ? (
                <View style={styles.stepState}>
                  <Icon name={state.icon} size={12} color={state.color} />
                  <Text style={[styles.stepStateText, { color: state.color }]} numberOfLines={1}>
                    {state.text}
                  </Text>
                </View>
              ) : null}
            </View>
            {step.credits ? <Text style={styles.stepCredits}>{step.credits}</Text> : null}
          </Tap>
        );
      })}
      {proposed && latest ? (
        <View style={styles.planActions}>
          <Button label="Not Now" variant="secondary" onPress={onDismiss} style={{ flex: 1 }} />
          <Button label={`Approve · ${credits(run.total)}`} icon="checkmark" onPress={onApprove} busy={working} style={{ flex: 1.6 }} />
        </View>
      ) : proposed ? (
        <Text style={styles.planNote}>Waiting for approval</Text>
      ) : run.state === 'dismissed' ? (
        <Text style={styles.planNote}>Turned down</Text>
      ) : working ? (
        <View style={styles.planActions}>
          <Text style={[styles.planNote, { flex: 1 }]}>Queuing… keep the app open until every step is in line.</Text>
          <Button small variant="secondary" label="Stop" onPress={onStop} />
        </View>
      ) : run.steps.some((s) => s.error) && latest ? (
        <View style={styles.planActions}>
          <Button label="Try the Rest Again" icon="refresh" variant="tinted" onPress={onApprove} style={{ flex: 1 }} />
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separator,
    backgroundColor: colors.chrome,
  },
  titleBox: { flex: 1, alignItems: 'center' },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  title: { ...fonts.headline, color: colors.text, maxWidth: 220 },
  subtitle: { ...fonts.caption, color: colors.textSecondary, maxWidth: 260 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xl },
  errorText: { ...fonts.subhead, color: colors.danger, textAlign: 'center' },
  log: { padding: spacing.lg, gap: spacing.lg, flexGrow: 1 },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: spacing.md, paddingVertical: spacing.xxl },
  emptyIcon: { width: 64, height: 64, borderRadius: 20, alignItems: 'center', justifyContent: 'center', marginBottom: spacing.sm },
  emptyTitle: { ...fonts.title2, color: colors.text },
  emptyText: { ...fonts.subhead, color: colors.textSecondary, textAlign: 'center', paddingHorizontal: spacing.xl },
  suggestions: { gap: spacing.sm, alignSelf: 'stretch', marginTop: spacing.lg },
  suggestion: { backgroundColor: colors.surface, borderRadius: radius.md, paddingVertical: spacing.md, paddingHorizontal: spacing.lg },
  suggestionText: { ...fonts.subhead, color: colors.text },
  turn: { gap: spacing.md },
  mine: { alignItems: 'flex-end', paddingLeft: 48 },
  mineBubble: { borderRadius: 20, borderBottomRightRadius: 6, paddingHorizontal: spacing.lg, paddingVertical: 10 },
  mineText: { ...fonts.body, color: colors.onBrand },
  theirs: { flexDirection: 'row', gap: spacing.sm, alignItems: 'flex-start', paddingRight: spacing.sm },
  agentAvatar: { width: 28, height: 28, borderRadius: 14, backgroundColor: colors.accent, alignItems: 'center', justifyContent: 'center', marginTop: 2 },
  theirsBody: { flex: 1, gap: spacing.sm },
  reply: { backgroundColor: colors.surface, borderRadius: 20, borderTopLeftRadius: 6, paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
  replyError: { backgroundColor: colors.dangerSoft },
  workToggle: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingLeft: 4 },
  workToggleText: { ...fonts.caption, color: colors.textMuted },
  work: { paddingLeft: spacing.md, gap: 2 },
  workLine: { ...fonts.caption, color: colors.textSecondary },
  question: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.md },
  questionText: { ...fonts.subheadStrong, color: colors.text },
  options: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  plan: { backgroundColor: colors.surface, borderRadius: radius.lg, overflow: 'hidden' },
  planHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: spacing.lg, paddingBottom: spacing.sm },
  planTitle: { ...fonts.headline, color: colors.text },
  planTotal: { ...fonts.subheadStrong, color: colors.accent },
  step: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
  stepLine: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.separator },
  stepIcon: { width: 44, height: 44, borderRadius: 10, backgroundColor: colors.accentSoft, alignItems: 'center', justifyContent: 'center' },
  stepThumb: { width: 44, height: 44, borderRadius: 10 },
  stepName: { ...fonts.subheadStrong, color: colors.text },
  stepPrompt: { ...fonts.footnote, color: colors.textSecondary },
  stepState: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  stepStateText: { ...fonts.caption },
  stepCredits: { ...fonts.footnoteStrong, color: colors.textSecondary },
  planActions: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, padding: spacing.md, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.separator },
  planNote: { ...fonts.footnote, color: colors.textSecondary, padding: spacing.md, paddingHorizontal: spacing.lg },
  thinking: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginTop: spacing.lg },
  thinkingBubble: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: spacing.md, backgroundColor: colors.surface, borderRadius: 20, borderTopLeftRadius: 6, paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
  dots: { flexDirection: 'row', gap: 4 },
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.textSecondary },
  thinkingText: { ...fonts.footnote, color: colors.textSecondary, flex: 1 },
  composer: { paddingHorizontal: spacing.md, paddingTop: spacing.sm, backgroundColor: colors.chrome, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.separator },
  inputBox: { flexDirection: 'row', alignItems: 'flex-end', gap: spacing.sm, backgroundColor: colors.surface, borderRadius: 22, paddingLeft: spacing.lg, paddingRight: 5, paddingVertical: 5 },
  input: { flex: 1, ...fonts.body, color: colors.text, maxHeight: 120, paddingVertical: 7 },
  sendButton: { width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center' },
});
