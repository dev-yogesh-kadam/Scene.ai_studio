import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as Haptics from '@/lib/haptics';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import Animated, { FadeIn, LinearTransition } from 'react-native-reanimated';

import { asReference } from '@scene/shared/api/library';
import { createJob, estimate, listWorkflows } from '@scene/shared/api/runs';
import { Banner } from '@/components/Banner';
import { Button } from '@/components/Button';
import { ChipRow } from '@/components/Chip';
import { EmptyState } from '@/components/EmptyState';
import { Icon, kindIcons, type IconName } from '@/components/Icon';
import { RefSlot, type RefChoice } from '@/components/RefPicker';
import { Segmented } from '@/components/Segmented';
import { Skeleton } from '@/components/Skeleton';
import { Tap } from '@/components/Tap';
import { LargeTitle, TitledScreen, useScrollY } from '@/components/TitledScreen';
import { useToast } from '@/components/Toast';
import { Toggle } from '@/components/Toggle';
import { useSession } from '@/hooks/useSession';
import { credits } from '@scene/shared/format';
import { colors, fonts, kindColors, lines, radius, spacing } from '@/theme';
import type { Control, JobSettings, Kind, Workflow } from '@scene/shared/types/api';
import { Alert } from '@/lib/dialog';

const KINDS: { value: Kind; label: string; icon: IconName }[] = [
  { value: 'video', label: 'Video', icon: 'film' },
  { value: 'image', label: 'Image', icon: 'image' },
  { value: 'audio', label: 'Music', icon: 'musical-notes' },
];

const ORIENTATIONS: { value: string; label: string; icon: IconName }[] = [
  { value: 'landscape', label: 'Landscape', icon: 'tablet-landscape-outline' },
  { value: 'portrait', label: 'Portrait', icon: 'phone-portrait-outline' },
  { value: 'square', label: 'Square', icon: 'square-outline' },
];

type Values = Record<string, unknown>;

function startValues(workflow: Workflow, prompt?: string): Values {
  const values: Values = {};
  for (const control of workflow.controls) {
    values[control.id] = control.role === 'prompt' ? (prompt ?? '') : control.default;
  }
  return values;
}

export default function CreateScreen() {
  const params = useLocalSearchParams<{ workflow?: string; prompt?: string; kind?: Kind }>();
  const queryClient = useQueryClient();
  const toast = useToast();
  const { user } = useSession();
  const { scrollY, onScroll } = useScrollY();
  const workflows = useQuery({ queryKey: ['workflows'], queryFn: listWorkflows, staleTime: 5 * 60_000 });
  const all = useMemo(() => workflows.data?.workflows ?? [], [workflows.data]);

  const [kind, setKind] = useState<Kind>('video');
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [values, setValues] = useState<Values>({});
  const [options, setOptions] = useState<Record<string, string>>({});
  const [orientation, setOrientation] = useState<string | undefined>();
  const [resolution, setResolution] = useState<number | undefined>();
  const [refs, setRefs] = useState<Record<string, RefChoice>>({});
  const [moreRefs, setMoreRefs] = useState(false);

  const ofKind = all.filter((w) => w.kind === kind);
  const workflow = all.find((w) => w.id === workflowId) ?? null;

  function choose(next: Workflow, prompt?: string) {
    // The prompt carries over when switching models: you shouldn't have to type it twice.
    const typed = prompt ?? (workflow ? String(values[promptControl(workflow)?.id ?? ''] ?? '') : '');
    setWorkflowId(next.id);
    setKind(next.kind);
    setValues(startValues(next, typed));
    setOptions(Object.fromEntries(next.options.map((o) => [o.id, o.default])));
    setOrientation(next.size?.orientation);
    setResolution(next.size ? next.resolutions.find((r) => r === next.size?.resolution) ?? next.resolutions[0] : undefined);
    setRefs({});
    setMoreRefs(false);
  }

  // "Make again" from the player, a kind from Home's quick buttons, or else the first model of the list.
  useEffect(() => {
    if (!all.length) return;
    const asked = params.workflow ? all.find((w) => w.id === params.workflow) : null;
    const ofAsked = params.kind && params.kind !== workflow?.kind ? all.find((w) => w.kind === params.kind) : null;
    if (asked) {
      choose(asked, params.prompt);
      router.setParams({ workflow: undefined, prompt: undefined });
    } else if (ofAsked) {
      choose(ofAsked);
      router.setParams({ kind: undefined });
    } else if (!workflowId) {
      choose(all.find((w) => w.kind === kind) ?? all[0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [all, params.workflow, params.kind]);

  const settings: JobSettings | null = workflow
    ? { workflow: workflow.id, values, options, ...(orientation ? { orientation } : {}), ...(resolution ? { resolution } : {}) }
    : null;
  const promptId = workflow ? promptControl(workflow)?.id ?? '' : '';
  const prompt = String(values[promptId] ?? '');

  // The price, asked again when the settings change (after a short pause in typing).
  const [priced, setPriced] = useState<JobSettings | null>(null);
  useEffect(() => {
    const timer = setTimeout(() => setPriced(settings), 400);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(settings)]);
  const price = useQuery({
    queryKey: ['estimate', priced],
    queryFn: () => estimate(priced!),
    enabled: !!priced,
    placeholderData: (previous) => previous,
  });

  const generate = useMutation({
    // A slot filled from the library goes as the file already on the render server; one from the phone goes along.
    mutationFn: async () => {
      const fromLibrary: Record<string, { comfy_name: string; name: string }> = {};
      const fromPhone: Record<string, { uri: string; name: string; type: string }> = {};
      for (const [slot, choice] of Object.entries(refs)) {
        if ('item' in choice) fromLibrary[slot] = await asReference(choice.item.id, workflow!.refs.find((r) => r.id === slot)?.kind);
        else fromPhone[slot] = { uri: choice.phone.uri, name: choice.phone.name, type: choice.phone.type };
      }
      return createJob({ ...settings!, refs: fromLibrary, name: nameFrom(prompt, workflow!) }, fromPhone);
    },
    onSuccess: (answer) => {
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      toast(`Started · ${credits(answer.credits)}`, { icon: 'sparkles' });
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
      void queryClient.invalidateQueries({ queryKey: ['credits'] });
      setValues({ ...values, [promptId]: '' });
      setRefs({});
      router.navigate('/activity');
    },
    onError: (error) => {
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      Alert.alert("Couldn't Start It", error.message);
    },
  });

  const cost = price.data?.credits;
  const balance = price.data?.balance ?? user?.credits;
  const short = cost != null && balance != null && cost > balance;
  const needed = workflow ? workflow.refs.filter((r) => !r.optional) : [];
  const missing = needed.filter((r) => !refs[r.id]);
  const wantsWords = !!workflow && !!promptId && !workflow.prompt_optional;
  const ready = !!workflow && (!wantsWords || prompt.trim().length > 0) && !missing.length && !short;
  // The slots shown: every one it needs, then a few optional ones (more on request).
  const optional = workflow ? workflow.refs.filter((r) => r.optional) : [];
  const slots = workflow ? [...needed, ...(moreRefs ? optional : optional.slice(0, 3))] : [];

  const kinds = KINDS.filter((k) => all.some((w) => w.kind === k.value));
  const others = workflow ? workflow.controls.filter((c) => c.role !== 'prompt') : [];

  return (
    <TitledScreen title="Create" scrollY={scrollY}>
      <KeyboardAvoidingView behavior="height" style={{ flex: 1 }}>
        <Animated.ScrollView onScroll={onScroll} scrollEventThrottle={16} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag">
          <LargeTitle title="Create" subtitle="Describe it, and the studio makes it" scrollY={scrollY} />

          {workflows.isPending ? (
            <View style={styles.section}>
              <Skeleton style={{ height: 36, borderRadius: 10 }} />
              <Skeleton style={{ height: 120, borderRadius: radius.lg }} />
              <Skeleton style={{ height: 160, borderRadius: radius.lg }} />
            </View>
          ) : !all.length ? (
            <View style={styles.section}>
              {workflows.error ? <Banner tone="danger" text={workflows.error.message} /> : null}
              <EmptyState icon="sparkles-outline" title="Nothing to Make Yet" text="An admin can turn on models in the studio. Models that start from a picture or a video are in the studio only." />
            </View>
          ) : (
            <>
              {kinds.length > 1 ? (
                <View style={styles.section}>
                  <Segmented
                    options={kinds}
                    value={kind}
                    onChange={(next) => {
                      setKind(next);
                      const first = all.find((w) => w.kind === next);
                      if (first) choose(first);
                    }}
                  />
                </View>
              ) : null}

              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.models} decelerationRate="fast" snapToInterval={172 + spacing.md}>
                {ofKind.map((w, index) => {
                  const on = w.id === workflowId;
                  return (
                    <Animated.View key={w.id} entering={FadeIn.duration(200)}>
                      <Tap
                        onPress={() => choose(w)}
                        haptic="selection"
                        scaleTo={0.95}
                        style={[styles.model, on && styles.modelOn]}
                        accessibilityLabel={`${shortTitle(w.title)}. ${w.description}`}
                        accessibilityState={{ selected: on }}>
                        <View style={styles.modelTop}>
                          <View style={[styles.modelIcon, { backgroundColor: kindColors[w.kind] + '26' }]}>
                            <Icon name={kindIcons[w.kind] ?? 'sparkles'} size={17} color={kindColors[w.kind]} />
                          </View>
                          {on ? (
                            <Animated.View entering={FadeIn.duration(150)}>
                              <Icon name="checkmark-circle" size={22} color={colors.accent} />
                            </Animated.View>
                          ) : null}
                        </View>
                        <Text style={styles.modelTitle} numberOfLines={2}>
                          {shortTitle(w.title)}
                        </Text>
                        <Text style={styles.modelText} numberOfLines={3}>
                          {w.description}
                        </Text>
                      </Tap>
                    </Animated.View>
                  );
                })}
              </ScrollView>

              {workflow ? (
                <Animated.View key={workflow.id} entering={FadeIn.duration(200)} layout={LinearTransition.duration(200)} style={styles.section}>
                  {promptId ? (
                  <View style={styles.promptCard}>
                    <TextInput
                      style={styles.prompt}
                      placeholder={placeholderFor(workflow)}
                      placeholderTextColor={colors.textMuted}
                      value={prompt}
                      onChangeText={(text) => setValues({ ...values, [promptId]: text })}
                      multiline
                      textAlignVertical="top"
                      maxLength={4000}
                    />
                    <View style={styles.promptFooter}>
                      {workflow.hints[0] ? (
                        <View style={styles.tip}>
                          <Icon name="bulb-outline" size={14} color={colors.warning} />
                          <Text style={styles.tipText} numberOfLines={2}>
                            {workflow.hints[0]}
                          </Text>
                        </View>
                      ) : (
                        <View style={{ flex: 1 }} />
                      )}
                      {prompt ? (
                        <Tap onPress={() => setValues({ ...values, [promptId]: '' })} hitSlop={10} accessibilityLabel="Clear the prompt">
                          <Icon name="close-circle" size={20} color={colors.textMuted} />
                        </Tap>
                      ) : null}
                    </View>
                  </View>
                  ) : null}

                  {slots.length ? (
                    <View style={styles.refs}>
                      <View style={styles.refsHeader}>
                        <Text style={styles.label}>{needed.length ? 'Start From' : 'References'}</Text>
                        {optional.length > 3 && !moreRefs ? (
                          <Tap onPress={() => setMoreRefs(true)} hitSlop={8}>
                            <Text style={styles.more}>{optional.length - 3} more</Text>
                          </Tap>
                        ) : null}
                      </View>
                      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.refRow}>
                        {slots.map((slot) => (
                          <RefSlot
                            key={slot.id}
                            label={slot.label}
                            kind={slot.kind}
                            optional={slot.optional}
                            value={refs[slot.id]}
                            onChange={(choice) => {
                              const next = { ...refs };
                              if (choice) next[slot.id] = choice;
                              else delete next[slot.id];
                              setRefs(next);
                            }}
                          />
                        ))}
                      </ScrollView>
                      {missing.length ? <Text style={[styles.note, { paddingHorizontal: spacing.lg }]}>Add {missing.map((m) => m.label.replace(/\s*\(.*\)\s*$/, '').toLowerCase()).join(', ')} to start.</Text> : null}
                    </View>
                  ) : null}

                  {others.length || workflow.size || workflow.options.length ? (
                    <View style={styles.settings}>
                      {others.map((control) => (
                        <ControlField key={control.id} control={control} value={values[control.id]} onChange={(value) => setValues({ ...values, [control.id]: value })} />
                      ))}
                      {workflow.size ? (
                        <Setting label="Shape">
                          <ChipRow padded={false} options={ORIENTATIONS} value={orientation ?? 'landscape'} onChange={setOrientation} />
                        </Setting>
                      ) : null}
                      {workflow.size && workflow.resolutions.length > 1 ? (
                        <Setting label="Resolution">
                          <ChipRow
                            padded={false}
                            options={workflow.resolutions.map((r) => ({ value: r, label: `${r}p` }))}
                            value={resolution ?? workflow.resolutions[0]}
                            onChange={setResolution}
                          />
                        </Setting>
                      ) : null}
                      {workflow.options.map((option) => {
                        const chosen = options[option.id] ?? option.default;
                        const hint = option.choices.find((c) => c.id === chosen)?.hint;
                        return (
                          <Setting key={option.id} label={option.label} note={hint}>
                            <ChipRow
                              padded={false}
                              options={option.choices.map((c) => {
                                const each = price.data?.choices?.[option.id]?.[c.id];
                                return { value: c.id, label: c.label, note: each != null ? String(each) : undefined };
                              })}
                              value={chosen}
                              onChange={(value) => setOptions({ ...options, [option.id]: value })}
                            />
                          </Setting>
                        );
                      })}
                    </View>
                  ) : null}
                </Animated.View>
              ) : null}
            </>
          )}
        </Animated.ScrollView>

        {all.length ? (
          <View style={styles.footer}>
            <View style={styles.price}>
              {cost == null ? (
                price.isFetching ? <ActivityIndicator color={colors.textSecondary} size="small" /> : null
              ) : (
                <Animated.View key={cost} entering={FadeIn.duration(200)}>
                  <Text style={[styles.cost, short && { color: colors.danger }]}>{cost.toLocaleString()} cr</Text>
                  <Text style={styles.balance}>
                    {short ? `You have ${credits(balance ?? 0)}` : price.data?.minutes ? `about ${Math.ceil(price.data.minutes)} min` : `of ${credits(balance ?? 0)}`}
                  </Text>
                </Animated.View>
              )}
            </View>
            <Button label="Generate" icon="sparkles" onPress={() => generate.mutate()} busy={generate.isPending} disabled={!ready} style={styles.go} />
          </View>
        ) : null}
      </KeyboardAvoidingView>
    </TitledScreen>
  );
}

function promptControl(workflow: Workflow) {
  return workflow.controls.find((c) => c.role === 'prompt');
}

function placeholderFor(workflow: Workflow) {
  const label = promptControl(workflow)?.label ?? '';
  return label.length > 12 && label.length < 110 && label !== label.toUpperCase() ? label : 'Describe what you want to see…';
}

/** A job's name: the first words of the prompt, as the studio's list shows it. */
function nameFrom(prompt: string, workflow: Workflow) {
  const words = prompt.trim().split(/\s+/).slice(0, 6).join(' ');
  return (words.length > 48 ? words.slice(0, 48) + '…' : words) || shortTitle(workflow.title);
}

/** "Text to Image: FLUX.2 dev" reads as "FLUX.2 dev" once the kind is already chosen. */
function shortTitle(title: string) {
  return title.includes(':') ? title.split(':').slice(1).join(':').trim() : title;
}

function Setting({ label, note, children, inline }: { label: string; note?: string; children: ReactNode; inline?: boolean }) {
  return (
    <View style={[styles.setting, inline && styles.settingInline]}>
      <Text style={[styles.label, inline && { flex: 1 }]}>{label}</Text>
      {children}
      {note ? <Text style={styles.note}>{note}</Text> : null}
    </View>
  );
}

function ControlField({ control, value, onChange }: { control: Control; value: unknown; onChange: (value: unknown) => void }) {
  const label = control.label.replace(/\s*\(optional\)\s*$/i, '').replace(/\s*\(.*\)\s*$/, '');
  const pretty = label === label.toUpperCase() ? label.charAt(0) + label.slice(1).toLowerCase() : label;
  if (control.choices?.length) {
    return (
      <Setting label={pretty}>
        <ChipRow
          padded={false}
          options={control.choices.map((c) => ({ value: c, label: control.role === 'duration' || /second/i.test(label) ? `${c}s` : String(c) }))}
          value={value as string | number}
          onChange={onChange}
        />
      </Setting>
    );
  }
  if (control.type === 'bool') {
    return (
      <Setting label={pretty} inline>
        <Toggle value={!!value} onChange={onChange} />
      </Setting>
    );
  }
  if (control.type === 'int' || control.type === 'float') {
    const number = Number(value ?? 0);
    const step = control.role === 'duration' || control.type === 'int' ? 1 : 0.5;
    return (
      <Setting label={pretty} inline>
        <View style={styles.stepper}>
          <Tap onPress={() => onChange(Math.max(1, number - step))} haptic="selection" scaleTo={0.85} style={styles.stepButton} hitSlop={6} accessibilityLabel={`Less ${pretty}`}>
            <Icon name="remove" size={18} />
          </Tap>
          <View style={styles.stepDivider} />
          <Text style={styles.stepValue}>
            {number}
            {control.role === 'duration' ? 's' : ''}
          </Text>
          <View style={styles.stepDivider} />
          <Tap onPress={() => onChange(number + step)} haptic="selection" scaleTo={0.85} style={styles.stepButton} hitSlop={6} accessibilityLabel={`More ${pretty}`}>
            <Icon name="add" size={18} />
          </Tap>
        </View>
      </Setting>
    );
  }
  return (
    <Setting label={pretty}>
      <TextInput style={styles.multiline} value={String(value ?? '')} onChangeText={onChange} multiline textAlignVertical="top" placeholderTextColor={colors.textMuted} />
    </Setting>
  );
}

const styles = StyleSheet.create({
  content: { paddingBottom: spacing.xxl, gap: spacing.lg },
  section: { paddingHorizontal: spacing.lg, gap: spacing.lg },
  models: { paddingHorizontal: spacing.lg, gap: spacing.md },
  model: { width: 172, minHeight: 148, padding: spacing.md, gap: 6, borderRadius: radius.lg, backgroundColor: colors.surface, borderWidth: 2, borderColor: 'transparent' },
  modelOn: { borderColor: colors.accent },
  modelTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 },
  modelIcon: { width: 32, height: 32, borderRadius: 9, alignItems: 'center', justifyContent: 'center' },
  modelTitle: { ...fonts.subheadStrong, color: colors.text },
  modelText: { ...fonts.caption, color: colors.textSecondary },
  refs: { backgroundColor: colors.surface, borderRadius: radius.lg, paddingVertical: spacing.lg, gap: spacing.md },
  refsHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: spacing.lg },
  refRow: { paddingHorizontal: spacing.lg, gap: spacing.md },
  more: { ...fonts.subhead, color: colors.accent },
  promptCard: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.md },
  prompt: { ...fonts.body, fontSize: 18, lineHeight: lines(26), color: colors.text, minHeight: 130, padding: 0 },
  promptFooter: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  tip: { flex: 1, flexDirection: 'row', gap: 6, alignItems: 'flex-start' },
  tipText: { ...fonts.caption, color: colors.textSecondary, flex: 1 },
  settings: { backgroundColor: colors.surface, borderRadius: radius.lg, paddingVertical: spacing.xs },
  setting: { paddingHorizontal: spacing.lg, paddingVertical: spacing.md, gap: spacing.sm },
  settingInline: { flexDirection: 'row', alignItems: 'center' },
  label: { ...fonts.subheadStrong, color: colors.text },
  note: { ...fonts.footnote, color: colors.textSecondary },
  multiline: { ...fonts.body, color: colors.text, backgroundColor: colors.surfaceRaised, borderRadius: radius.md, padding: spacing.md, minHeight: 90 },
  stepper: { flexDirection: 'row', alignItems: 'center', backgroundColor: colors.fill, borderRadius: 9, height: 34 },
  stepButton: { width: 44, height: 34, alignItems: 'center', justifyContent: 'center' },
  stepDivider: { width: StyleSheet.hairlineWidth, height: 18, backgroundColor: colors.separator },
  stepValue: { ...fonts.subheadStrong, color: colors.text, minWidth: 44, textAlign: 'center' },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.lg,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.separator,
    backgroundColor: colors.chrome,
  },
  price: { minWidth: 92 },
  cost: { ...fonts.title3, color: colors.text },
  balance: { ...fonts.caption, color: colors.textSecondary },
  go: { flex: 1 },
});
