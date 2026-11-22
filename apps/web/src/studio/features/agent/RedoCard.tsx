// The steps of a plan that were not made (a shot the provider refused, one that started on it, the cut that waited),
// offered again in the dock above the message box for the user to approve: each with why it was not made and what is
// changed so it can be (a resolution its model needs with references), and the price. Make again resumes the plan
// (the same plan, so the finished cut still follows); Not now puts the card away and leaves a Resume in the chat.

import { useEffect, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { planRedo, type PlanRedo } from '@scene/shared/api/agent';
import { Icon } from '../../../common/components/Icon/Icon';
import { cx } from '../../../common/cx';
import { approve } from './actions';
import type { AgentChat } from './chat';
import { takesOf } from './shots';
import type { Run, Step } from './types';
import s from './Ask.module.css';

const ENDED_BADLY = ['failed', 'cancelled'];

/** A step of an approved plan that was not made: never queued, or its job failed or was cancelled (a provider that
 *  refused the clip). A step with a take made (a retake) is made. */
export const notMade = (chat: AgentChat, step: Step) =>
  !step.skipped &&
  !takesOf(step).some((take) => take.made) &&
  (!step.job || ENDED_BADLY.includes(chat.jobOf(step.job)?.status ?? ''));

/** Whether a plan has steps that were not made and nothing of it is still being made: the dock offers them again.
 *  (A failed shot keeps its failed job, so "no job" alone missed every shot the provider refused.) */
export const unfinished = (chat: AgentChat, run: Run | undefined) =>
  !!run && run.state === 'approved' && !chat.generating() && run.steps.some((step) => notMade(chat, step));

/** Make the steps not made again: their failed jobs are let go (as a shot's own Try again does) and the plan resumes,
 *  the same plan, so a cut that waits on them still follows. */
export function makeAgain(chat: AgentChat, run: Run) {
  for (const step of run.steps)
    if (notMade(chat, step) && step.job) chat.patch(step, { job: null, queuedAt: null, error: null });
  return approve(chat, run);
}

export const redoOpen = (chat: AgentChat, run: Run | undefined) =>
  !!run &&
  chat.runs[chat.runs.length - 1] === run &&
  !!run.plan &&
  !chat.working &&
  !chat.pending &&
  !run.ui.redoClosed &&
  unfinished(chat, run);

export function RedoCard({ chat, run }: { chat: AgentChat; run: Run }) {
  const [found, setFound] = useState<PlanRedo | null>(null);
  const [problem, setProblem] = useState('');
  const plan = run.plan;
  useEffect(() => {
    if (!plan) return;
    let live = true;
    planRedo(plan)
      .then((answer) => live && setFound(answer))
      .catch((e: Error) => live && setProblem(e.message));
    return () => {
      live = false;
    };
  }, [plan]);
  const close = () => chat.patch(run.ui, { redoClosed: true });
  const short = !!found && found.total > chat.credits;
  const go = () => {
    if (!found || chat.working || short) return;
    void makeAgain(chat, run);
  };
  const keys = (e: ReactKeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      go();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      close();
    }
  };
  const made = found?.steps.filter((x) => x.maker !== 'Final cut') || []; // the cut follows by itself
  const count = made.length;
  return (
    <div className={s['ask-card']} role="group" aria-label="Steps to make again" tabIndex={-1} onKeyDown={keys}>
      <div className={s['ask-head']}>
        <Icon name="retry" />
        <b>
          {!found
            ? 'Not every step was made'
            : count === 1
              ? `Make “${made[0].name}” again?`
              : `Make these ${count} steps again?`}
        </b>
      </div>
      <div className={s['ask-options']}>
        {!found && !problem && <p className={cx('muted small', s['ask-detail'])}>Pricing what is left…</p>}
        {problem && <p className={cx('small', s['ask-detail'])}>{problem}</p>}
        {found?.steps.map((step) => (
          <div key={step.step} className={cx(s['ask-option'], s['ask-shot'], s.on)}>
            <span className={s['ask-tick']}>
              <span className={s['ask-words']}>
                <b>
                  {step.name}
                  {step.maker && <span className="muted"> · {step.maker}</span>}
                </b>
                {step.note && <span className={s['ask-detail']}>{step.note}</span>}
                {step.reason && <span className={cx('muted', s['ask-detail'])}>Was not made: {step.reason}</span>}
              </span>
            </span>
          </div>
        ))}
      </div>
      <div className={s['ask-foot']}>
        <span style={{ flex: 1 }} />
        <button type="button" className="btn small quiet" onClick={close}>
          Not now
          <kbd>esc</kbd>
        </button>
        <button
          type="button"
          className="btn small primary"
          disabled={!found || chat.working || short || !found.steps.length}
          title={short ? `Needs ${found?.total} credits, you have ${chat.credits}` : `You have ${chat.credits} credits`}
          onClick={go}
        >
          {count === 1 ? 'Make it again' : 'Make again'}
          {found ? ` · ${found.total} cr` : ''}
          <kbd>↵</kbd>
        </button>
      </div>
    </div>
  );
}
