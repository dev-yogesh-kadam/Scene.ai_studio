// The agent looks at what it made. Finished jobs become their library items; once everything a plan queued has come to
// an end its shots are checked together, a few at a time; what the checks found is dealt with under the permission the
// plan ran under; and a long skill's run goes on by itself. Exactly the classic page's rules: review and retakes stay
// on the page, the plan itself runs on the server.

import { asReference } from '@scene/shared/api/library';
import { madeBy } from '@scene/shared/api/items';
import { reviewItem } from '@scene/shared/api/agent';
import { api } from '../../../common/api';
import type { Item } from '../../../common/media/item';
import type { AgentChat } from './chat';
import {
  CHECK_RESULTS,
  MAX_RETAKES,
  REVIEW_TIMEOUT,
  REVIEW_WITHIN,
  REVIEWS_AT_ONCE,
  SAVED_ONLY,
  bestTake,
  retakesOf,
  shotsOf,
  takesOf,
  usedTake,
} from './shots';
import type { Retake, Review, Run, Step, Take } from './types';

/** Whether a finished take is still to be checked (one finished long ago is not, when the panel opens). */
export function toCheck(chat: AgentChat, take: Take | null | undefined) {
  if (!CHECK_RESULTS) return false;
  if (!take || !take.job || take.review || take.reviewing || take.reviewError) return false;
  const job = chat.jobOf(take.job);
  return !!job && job.status === 'done' && Date.now() - (take.queuedAt || 0) < REVIEW_WITHIN;
}

/** Whether everything a plan queued, retakes too, has come to an end: only then are its shots checked, together. */
export function allMade(chat: AgentChat, run: Run) {
  return (
    !chat.working &&
    run.steps.every(
      (step) =>
        step.skipped ||
        takesOf(step).every((take) => {
          if (!take.job) return take === step || !!take.error;
          const job = chat.jobOf(take.job);
          return !job || (job.status !== 'queued' && job.status !== 'running');
        }),
    )
  );
}

export const checking = (chat: AgentChat, run: Run) =>
  CHECK_RESULTS && shotsOf(run).some((s) => takesOf(s).some((t) => t.reviewing || toCheck(chat, t)));

/** Whether a step is done with for the run: a picture or a clip once its check is over and, when the check failed,
 *  once the user chose. A check that could not run, or a failed one with no retake to offer, never holds the run. */
export function settled(chat: AgentChat, step: Step) {
  if (!CHECK_RESULTS) return true; // nothing is checked: a made shot is done with
  if (step.skipped || !step.settings || (step.kind !== 'image' && step.kind !== 'video')) return true;
  const take = step.take2 || step;
  if (take.reviewing) return false;
  if (take.reviewError) return true;
  if (!take.review) {
    // a shot that finished lately is about to be checked; an old one is not
    if (take !== step && !take.job && !take.error) return false; // a retake on its way to the queue
    const job = chat.jobOf(take.job);
    return !(job && job.status === 'done' && Date.now() - (take.queuedAt || 0) < REVIEW_WITHIN);
  }
  return take.review.passed || take !== step || !!step.kept || !step.retake;
}

/** A long skill's run goes on by itself: once every step of its newest plan has come to an end, the agent is told what
 *  each made, by library id, and carries on. Once per plan; it waits while anything is being made or the agent is busy. */
export function carryOn(chat: AgentChat) {
  const run = chat.runs[chat.runs.length - 1];
  // Answers given while shots were being made: sent alone once the box is free, when the run does not go on by itself...
  if (run && run.queuedAnswer && !chat.busy && !chat.generating() && (!run.continues || run.continued)) {
    const typed = run.queuedAnswer;
    delete run.queuedAnswer;
    void chat.save();
    void chat.send(typed);
    return;
  }
  if (!run || !run.continues || run.continued || chat.busy || chat.generating() || chat.halted) return;
  // ...or with the run's next message, when it goes on.
  const answers = () => {
    const typed = run.queuedAnswer;
    delete run.queuedAnswer;
    return typed ? `\n\nThe user answered your questions meanwhile:\n${typed.text}` : '';
  };
  // A turn that saved its work and planned nothing goes on at once, at most SAVED_ONLY times in a row.
  if (!run.steps.length) {
    const tail = chat.runs.slice().reverse();
    const inRow = tail.findIndex((r) => !(r.continues && !r.steps.length));
    if ((inRow === -1 ? tail.length : inRow) > SAVED_ONLY) return;
    run.continued = true;
    void chat.save();
    void chat.send({
      text:
        "Continue the run: you saved your work and planned nothing to make. Go on from the run's status." + answers(),
      shown: 'Continue the run',
      ids: [],
      parts: [{ text: 'Continue the run' }],
      auto: true,
    });
    return;
  }
  if (run.state !== 'approved') return;
  if (!run.steps.every((s) => settled(chat, s))) return; // a shot still being checked, or waiting for Retake or Keep it
  const lines: string[] = [];
  for (const step of run.steps) {
    if (step.skipped) {
      lines.push(`- “${step.name}”: skipped`);
      continue;
    }
    const all = takesOf(step);
    const newest = all[all.length - 1];
    const take = newest.made ? usedTake(step) : newest;
    const job = chat.jobOf(take.job);
    if (take.made && take.madeAll) {
      lines.push(`- “${step.name}”: ${take.madeAll.map((i) => `item ${i.id} (${i.kind}, “${i.name}”)`).join('; ')}`);
    } else if (take.made) {
      const info = take.madeInfo || {};
      const size = info.width ? `, ${info.width}×${info.height}` : '';
      const checked = take.review && !take.review.passed ? ` — its check: ${take.review.problem}` : '';
      lines.push(
        `- “${step.name}”: item ${take.made} (${step.kind}${size}${info.duration ? `, ${info.duration} s` : ''})${checked}`,
      );
    } else if (take.error || (job && (job.status === 'failed' || job.status === 'cancelled'))) {
      lines.push(`- “${step.name}”: not made — ${take.error || job?.error || job?.status}`);
    } else return; // still on its way
  }
  run.continued = true;
  void chat.save();
  const shown = `Continue the run (${run.steps.length} ${run.steps.length === 1 ? 'step' : 'steps'} done)`;
  void chat.send({
    text:
      `Continue the run. The steps you planned have come to an end:\n${lines.join('\n')}\n` +
      "Write what they made to the run's state, then go on from its status." +
      answers(),
    shown,
    ids: [],
    parts: [{ text: shown }],
    auto: true,
  });
}

/** Look at a finished shot: the server takes its frames and the agent's model checks them against the prompt, the
 *  references the shot was made with and, for a shot that continues another, the shot before. */
async function reviewStep(chat: AgentChat, run: Run, take: Take, step: Step, allowRetake: boolean) {
  take.reviewing = true;
  chat.changed();
  try {
    if (!take.made && take.job) take.made = (await madeBy<Item>(take.job, chat.env.project()))[0]?.id ?? null;
    if (!take.made) {
      // not in the library yet: look again in a moment, a few times
      take.reviewing = false;
      take.tries = (take.tries || 0) + 1;
      if (take.tries >= 5) take.reviewError = 'its result is not in the library.';
      setTimeout(() => reviewFinished(chat), 4000);
      chat.changed();
      return;
    }
    const before = step.after ? run.steps[step.after.step] : step.follows != null ? run.steps[step.follows] : null;
    const uses = (step.uses || []).map((use) => (use.asset ? { asset: use.asset } : { id: use.id }));
    // never waited for longer than REVIEW_TIMEOUT: a check that hangs would hold its place, and the rest, for good
    const found = await Promise.race([
      reviewItem<{ verdict: Review; retake?: Retake; retaken?: { job: string; credits: number } }>({
        item: take.made,
        prompt: take.prompt || step.prompt,
        uses,
        previous: before ? before.made || null : null,
        retake: allowRetake,
      }),
      new Promise<never>((_, fail) =>
        setTimeout(() => fail(new Error('the check took too long; the shot is kept as it is.')), REVIEW_TIMEOUT),
      ),
    ]);
    take.review = found.verdict;
    if (allowRetake) step.retake = found.retake;
    const which = take === step ? `“${step.name}”` : `the retake of “${step.name}”`;
    chat.work(
      run,
      'check',
      found.verdict.passed
        ? `Checked ${which}: it is what was asked for`
        : `Checked ${which}: ${found.verdict.problem}`,
    );
    if (found.retaken && take === step && !step.take2) {
      // made again once by itself while the panel was closed
      step.take2 = { prompt: found.verdict.fix?.prompt || step.prompt, queuedAt: Date.now(), job: found.retaken.job };
      chat.work(run, 'retry', `Retook “${step.name}” on its own · ${found.retaken.credits} cr`);
      chat.env.onJobs([found.retaken.job]);
      chat.env.queued();
    } else {
      take.toWeigh = true; // what it found is dealt with once every shot of the plan is checked (weigh)
      take.mayRetake = allowRetake;
    }
  } catch (e) {
    take.reviewError = (e as Error).message;
  }
  take.reviewing = false;
  reviewFinished(chat); // the next shot of the batch, or, the batch checked, what the checks found
  void chat.save();
  chat.changed();
  carryOn(chat); // the run may have been waiting for this check
}

/** Once every shot of a plan is checked, what the checks found is dealt with together. A retake runs under the same
 *  permission the plan ran under. What is asked goes in one card above the box. Never beyond the credits in hand. */
function weigh(chat: AgentChat, run: Run) {
  if (checking(chat, run)) return;
  const mode = chat.permission().id;
  for (const step of shotsOf(run)) {
    const take = step.take2 || step;
    if (!take.toWeigh) continue;
    delete take.toWeigh;
    let retook = false;
    const first = take === step;
    const again = !first && mode === 'all' && retakesOf(step) < MAX_RETAKES;
    if (take.mayRetake && !take.review?.passed && step.retake && !step.kept && (first || again)) {
      const auto = again || chat.retryOnce || mode === 'all' || (mode === 'videos' && step.kind !== 'video');
      // Credits already promised to other retakes of this batch count as spent. retake() releases the reservation.
      if (auto && step.retake.credits <= chat.credits - chat.reservedCredits) {
        chat.reservedCredits += step.retake.credits;
        chat.work(
          run,
          'retry',
          `Making “${step.name}” again (take ${retakesOf(step) + 2}) · ${step.retake.credits} cr`,
        );
        void retake(chat, run, step, true);
        retook = true;
      }
    }
    // A retake that failed too and is not made again: the best of the takes goes on, and the run with it.
    if (!first && !take.review?.passed && !retook) {
      const best = bestTake(step);
      step.chosen = best ? takesOf(step).indexOf(best) + 1 : step.chosen;
      chat.work(
        run,
        'check',
        `Going on with take ${step.chosen} of “${step.name}”, the best of ${takesOf(step).length}`,
      );
    }
  }
}

/** Check the shots of an approved plan once all of them have been made, each once. Edits, sounds and motion graphics
 *  are not reviewed: they are made from what the user already has. */
export function reviewFinished(chat: AgentChat) {
  if (!CHECK_RESULTS) return;
  let free =
    REVIEWS_AT_ONCE -
    chat.runs
      .flatMap((r) => shotsOf(r))
      .flatMap((s) => takesOf(s))
      .filter((t) => t.reviewing).length;
  for (const run of chat.runs) {
    if (run.state !== 'approved' || !allMade(chat, run)) continue;
    for (const step of shotsOf(run)) {
      // A retake is checked with a retake priced too while "Allow all" may still make it again.
      const more = chat.permission().id === 'all' && retakesOf(step) < MAX_RETAKES;
      for (const [take, first] of [
        [step, true],
        [step.take2, more],
      ] as [Take | null | undefined, boolean][]) {
        if (!toCheck(chat, take)) continue;
        if (free <= 0) return; // the rest follow as these come back
        free -= 1;
        void reviewStep(chat, run, take as Take, step, first);
      }
    }
    weigh(chat, run);
  }
}

/** Finished jobs become their library items: the result shows, with its frames and its place on the canvas. */
export async function collectResults(chat: AgentChat) {
  // A job that finished while another collect was on its way is not dropped: it is collected once that one ends.
  if (chat.collecting) {
    chat.collectAgain = true;
    return;
  }
  const open: [Run, Step, Take][] = [];
  for (const run of chat.runs)
    for (const step of run.steps)
      for (const take of takesOf(step)) {
        if (!take || !take.job || take.made || (take.misses || 0) >= COLLECT_TRIES) continue;
        const job = chat.jobOf(take.job);
        if (!job || job.status === 'done') open.push([run, step, take]);
      }
  if (!open.length) return;
  chat.collecting = true;
  chat.collectAgain = false;
  let missed = false;
  try {
    // What each of those jobs made: only those items are asked for, not the whole canvas.
    const jobs = [...new Set(open.map(([, , take]) => take.job as string))];
    const made = new Map(
      await Promise.all(
        jobs.map(async (job) => [job, await madeBy<Item & { review?: string }>(job, chat.env.project())] as const),
      ),
    );
    // A job may save several files (a voice stem and the music; a transcript as JSON and SRT): all of them are kept.
    const allOf = (jobId: string) => [...(made.get(jobId) ?? [])].sort((a, b) => a.id - b.id);
    let found = false;
    for (const [run, step, take] of open) {
      const item = allOf(take.job as string)[0];
      if (!item) {
        // the job is done but its item is not saved yet: looked for again in a moment
        take.misses = (take.misses || 0) + 1;
        if (take.misses < COLLECT_TRIES) missed = true;
        continue;
      }
      const c = item.context || {};
      take.made = item.id;
      take.madeInfo = {
        duration: c.duration ? c.duration * (c.clips || 1) : null,
        width: c.width || null,
        height: c.height || null,
      };
      const every = allOf(take.job as string);
      if (every.length > 1) take.madeAll = every.map((i) => ({ id: i.id, kind: i.kind, name: i.name }));
      if (item.rating) take.rating = item.rating;
      chat.work(run, 'ready', take === step ? `“${step.name}” is ready` : `The retake of “${step.name}” is ready`);
      if (item.kind === 'audio' && item.review) {
        try {
          take.review = JSON.parse(item.review) as Review;
          chat.work(
            run,
            'check',
            take.review.passed
              ? `Checked the sound of “${step.name}”`
              : `Checked the sound of “${step.name}”: ${take.review.problem}`,
          );
        } catch {
          // not readable: no check shown
        }
      }
      found = true;
    }
    if (found) {
      void chat.save();
      chat.changed();
    }
  } catch {
    missed = true; // the server did not answer: tried again in a moment, not only on the next job update
  }
  chat.collecting = false;
  carryOn(chat);
  if (chat.collectAgain) {
    chat.collectAgain = false;
    void collectResults(chat);
  } else if (missed && !chat.collectRetry) {
    chat.collectRetry = setTimeout(() => {
      chat.collectRetry = null;
      void collectResults(chat);
      reviewFinished(chat);
    }, COLLECT_RETRY_MS);
  }
}

/** How often, and how far apart, a finished job's item is looked for before its take is given up on. */
const COLLECT_TRIES = 10;
const COLLECT_RETRY_MS = 3000;

/** The retake of a failed shot: the same workflow and settings with the prompt the review fixed. A retake made before
 *  it is kept with the earlier takes; the newest is step.take2. `reserved`: already counted by the automatic path. */
export async function retake(chat: AgentChat, run: Run, step: Step, reserved = false) {
  const plan = step.retake as Retake;
  if (step.take2) (step.earlier = step.earlier || []).push(step.take2);
  const take: Take = { prompt: plan.prompt, queuedAt: Date.now(), credits: plan.credits };
  step.take2 = take;
  chat.changed();
  const release = () => {
    if (reserved && Number.isFinite(plan.credits))
      chat.reservedCredits = Math.max(0, chat.reservedCredits - plan.credits);
  };
  try {
    const settings = { ...plan.settings, refs: { ...(plan.settings.refs || {}) } };
    if (plan.start) {
      // the review found that the cut jumps: the retake starts on the last frame of the shot before
      const ref = await asReference(plan.start.id);
      settings.refs[plan.start.slot] = { comfy_name: ref.comfy_name, name: ref.name };
    }
    const data = new FormData();
    data.append('settings', JSON.stringify(settings));
    take.job = (await api<{ id: string }>('/api/jobs', { method: 'POST', body: data })).id;
    // The server has now charged for it. The local balance drops by the same amount, so another shot reviewed in the
    // same burst sees what is really left; the next live update says the server's figure.
    if (Number.isFinite(plan.credits)) chat.credits = Math.max(0, chat.credits - plan.credits);
    release();
    chat.work(run, 'retry', `Queued a retake of “${step.name}”`);
    chat.env.onJobs(chat.startedJobs());
    chat.env.queued();
  } catch (e) {
    take.error = (e as Error).message;
    release();
  }
  void chat.save();
  chat.changed();
}
