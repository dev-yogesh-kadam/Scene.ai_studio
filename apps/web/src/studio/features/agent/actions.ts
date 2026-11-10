// What the user does with a plan. Approve hands the plan to the studio, which carries it out on the server with the
// page open or not (backend/scene/plans.py); where each step stands comes back on the live connection (applyPlans).
// A step can be changed before that (the server builds it again and prices it), and stages drawn: stills first, then
// the clips.

import {
  animate as animateShots,
  changeStep as sendStep,
  compactSession,
  getPlan,
  makePlan,
  rateItem,
  reroll as rerollStep,
  startPlan,
  stopPlan,
  storyboard as boardShots,
} from '@scene/shared/api/agent';
import { api } from '../../../common/api';
import type { AgentChat } from './chat';
import { GO, eligible, questionsOf, recount, usedTake } from './shots';
import type { Retake, Run, RunContext, ServerPlan, Step, Take, Typed } from './types';

export function applyPlan(chat: AgentChat, run: Run, plan: ServerPlan) {
  if (plan.id !== run.plan) return;
  plan.steps.forEach((shown, i) => {
    const step = run.steps[i];
    if (!step) return;
    if (shown.job && !step.job) {
      step.job = shown.job;
      step.queuedAt = step.queuedAt || Date.now();
      chat.work(run, 'queue', `Queued “${step.name}”`);
    }
    step.waiting = shown.waiting;
    if (shown.error && !step.error) {
      step.error = shown.error;
      chat.work(run, 'warn', `“${step.name}” was not made: ${shown.error}`);
    }
  });
  chat.working = plan.state === 'running' || plan.state === 'stopping';
  run.planState = plan.state;
  chat.env.onJobs(chat.startedJobs());
}

export function applyPlans(chat: AgentChat) {
  let changed = false;
  for (const run of chat.runs) {
    const plan = run.plan ? chat.plans.get(run.plan) : undefined;
    if (plan && plan !== run.seenPlan) {
      run.seenPlan = plan;
      applyPlan(chat, run, plan);
      changed = true;
    }
  }
  if (changed) {
    void chat.save();
    chat.changed();
  }
}

/** A plan the studio is still carrying out (or that ended while this page was closed): where it stands now. */
export function followPlans(chat: AgentChat) {
  for (const run of chat.runs.filter((r) => r.plan && !['done', 'failed', 'stopped'].includes(r.planState ?? ''))) {
    void getPlan<ServerPlan>(run.plan as number)
      .then((plan) => {
        chat.plans.set(plan.id, plan);
        applyPlans(chat);
      })
      .catch(() => {});
  }
}

/** Carry out an approved plan. One that stopped part way goes on from where it stopped: what is left is priced and
 *  reserved again. */
/** `auto`: the page approves it by itself, under the user's permission; refused by the server, it waits for Approve. */
export async function approve(chat: AgentChat, run: Run, auto = false) {
  const was = run.state;
  chat.working = true;
  chat.halted = false;
  run.state = 'approved';
  run.approvedAt = run.approvedAt || Date.now();
  chat.changed();
  try {
    if (!run.plan) {
      const made = await makePlan({
        steps: run.steps,
        name: run.title || '',
        tab: chat.talk,
        project_id: chat.env.project() || null,
      });
      run.plan = made.id;
      void chat.save();
    }
    const again = run.steps.some((step) => step.job || step.made || step.error);
    const plan = await startPlan<ServerPlan>(run.plan, again, auto);
    chat.plans.set(plan.id, plan);
    for (const step of run.steps) if (step.error && !step.made) step.error = null; // tried again
    run.seenPlan = plan;
    applyPlan(chat, run, plan);
    chat.env.queued();
  } catch (e) {
    chat.working = false;
    if (auto) run.state = was; // not started by itself: Approve is still there
    chat.work(run, 'warn', `The plan was not started: ${(e as Error).message}`);
  }
  void chat.save();
  chat.changed();
}

export async function stopGeneration(chat: AgentChat) {
  chat.halted = true;
  chat.changed();
  // The studio stops queueing the plans' steps; what is already queued is cancelled here.
  await Promise.all(
    chat.runs.filter((r) => r.plan && chat.working).map((r) => stopPlan(r.plan as number).catch(() => {})),
  );
  await Promise.all(chat.activeJobs().map((id) => api('/api/jobs/' + id, { method: 'DELETE' }).catch(() => {})));
  chat.env.queued();
  chat.changed();
}

/** Change one step on its card. The server builds it again with the same checks as a planned step, and prices it. */
export async function changeStep(
  chat: AgentChat,
  run: Run,
  index: number,
  change: Record<string, unknown>,
): Promise<void> {
  const step = run.steps[index];
  step.updating = true;
  step.error = null;
  chat.changed();
  try {
    const made = await sendStep<Step>(step, change);
    run.steps[index] = { ...made, name: step.name, open: step.open };
    // A shot that starts on this one takes its shape: a different shape would be stretched.
    if (change.orientation) {
      for (const [later, other] of run.steps.entries())
        if (other.after && other.after.step === index && other.menu?.shapes)
          await changeStep(chat, run, later, { orientation: change.orientation });
    }
  } catch (e) {
    step.error = (e as Error).message;
  }
  step.updating = false;
  recount(run);
  void chat.save();
  chat.changed();
}

export function toggleSkip(chat: AgentChat, run: Run, step: Step) {
  step.skipped = !step.skipped;
  recount(run);
  void chat.save();
  chat.changed();
}

/** What the user typed under a plan instead of approving it: the plan is set aside and the agent plans again with the
 *  change. A note that only says to go ahead is the Approve button. */
export function revise(chat: AgentChat, run: Run) {
  const note = String(run.ui.note || '').trim();
  if (!note || chat.busy || chat.working || run.state !== 'proposed') return;
  run.ui.note = '';
  if (GO.test(note)) {
    if (run.total <= chat.credits) void approve(chat, run);
    return;
  }
  run.state = 'dismissed';
  run.revised = note;
  void chat.save();
  void chat.send({
    text: `Change the plan you just proposed (it was not run): ${note}`,
    shown: note,
    ids: [],
    parts: [{ text: note }],
    from: run,
  });
}

/** Send what was picked: one answer as it is, several as a list. While shots are being made the box waits, so the
 *  answers are kept and go with the run's next message or on their own once it is free. */
export function answer(chat: AgentChat, run: Run, picked: string[]) {
  const list = questionsOf(run);
  let typed: Typed;
  if (run.question) {
    run.question.answer = picked[0];
    typed = { text: picked[0], shown: picked[0], ids: [], parts: [{ text: picked[0] }] };
  } else {
    run.picks = picked;
    run.questionsSent = true;
    const text = 'My answers:\n' + list.map((q, i) => `${i + 1}. ${q.text} — ${picked[i]}`).join('\n');
    typed = { text, shown: picked.join(' · '), ids: [], parts: [{ text }] };
  }
  if (chat.busy || chat.generating()) run.queuedAnswer = typed;
  void chat.save();
  if (run.queuedAnswer) chat.changed();
  else void chat.send(typed);
}

/** Thumbs on a result: saved with the item, and the agent reuses what was liked and never what was turned down. */
export async function rate(chat: AgentChat, take: Take, value: number) {
  const before = take.rating || 0;
  take.rating = before === value ? 0 : value;
  chat.changed();
  try {
    await rateItem(take.made as number, take.rating);
    void chat.save();
  } catch {
    take.rating = before;
    chat.changed();
  }
}

/** Another take of a finished shot: the same prompt with a new seed, priced first and made only when the user says so. */
export async function reroll(chat: AgentChat, step: Step) {
  step.rollBusy = true;
  step.rollError = null;
  chat.changed();
  try {
    step.rolling = (await rerollStep<Retake>(step.made as number)).retake;
  } catch (e) {
    step.rollError = (e as Error).message;
  }
  step.rollBusy = false;
  chat.changed();
}

type Staged = { steps: Step[]; total: number; dropped: [string, ...unknown[]][]; rest?: Step[] };

function propose(chat: AgentChat, run: Partial<Run> & Pick<Run, 'instruction' | 'reply' | 'steps'>) {
  const made: Run = {
    parts: [{ text: run.instruction }],
    thought: '',
    activity: [],
    seconds: 0,
    chips: {},
    total: 0,
    state: 'proposed',
    at: Date.now(),
    ui: {},
    llm: null,
    ...run,
  };
  chat.runs.push(made);
  recount(made);
  void chat.save();
}

const leftOut = (made: Staged) =>
  made.dropped.length ? ` Left out: ${made.dropped.map((d) => d[0]).join(', ')}.` : '';

export async function storyboard(chat: AgentChat, run: Run) {
  chat.boarding = true;
  chat.changed();
  try {
    const shots = eligible(run);
    const made = await boardShots<Staged>({
      project_id: chat.env.project() || null,
      shots: shots.map((s) => ({ shot_id: s.shot_id, proposal: s.proposal })),
    });
    // What is not a video shot (music, titles, an edit) waits for the clips, so it is carried to the next stage.
    const rest = run.steps.filter((s) => !shots.includes(s) && !s.skipped).map((s) => ({ ...s, after: null }));
    run.state = 'dismissed';
    run.revised = 'Storyboard first';
    propose(chat, {
      instruction: 'Storyboard first',
      reply:
        `Here are ${made.steps.length} stills, one for each shot, for ${made.total} credits. Approve to draw them, ` +
        `then choose the ones to animate.${leftOut(made)}`,
      steps: made.steps,
      rest,
    });
  } catch (e) {
    run.ui.note = '';
    chat.say((e as Error).message);
  }
  chat.boarding = false;
  chat.changed();
}

export async function animate(chat: AgentChat, run: Run) {
  chat.boarding = true;
  chat.changed();
  try {
    const stills = run.steps.filter((s) => s.stage === 'still' && s.made && !s.out);
    const made = await animateShots<Staged>({
      project_id: chat.env.project() || null,
      shots: stills.map((s) => ({ shot_id: s.shot_id, item: usedTake(s).made, proposal: s.proposal })),
    });
    if (!made.steps.length) throw new Error('None of the stills could be animated.');
    run.animated = true;
    propose(chat, {
      instruction: 'Animate the stills',
      reply:
        `Each still starts its clip: ${made.steps.length} ` +
        `${made.steps.length === 1 ? 'shot' : 'shots'} for ${made.total} credits. Approve to make them.${leftOut(made)}`,
      steps: [...made.steps, ...(run.rest || [])],
    });
  } catch (e) {
    chat.say((e as Error).message);
  }
  chat.boarding = false;
  chat.changed();
}

/** Compact this tab's Claude session now (it stays the same session; backend/scene/sessions.py). */
export async function compactContext(chat: AgentChat, run: Run) {
  const c = run.context as RunContext;
  c.compacting = true;
  chat.changed();
  try {
    const done = await compactSession<RunContext>({
      run: chat.env.session || 'main',
      project_id: chat.env.project() || null,
    });
    run.context = { ...done.context, compacted: true };
  } catch (e) {
    c.compacting = false;
    c.error = (e as Error).message;
  }
  void chat.save();
  chat.changed();
}
