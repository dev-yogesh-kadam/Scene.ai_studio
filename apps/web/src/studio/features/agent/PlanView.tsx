// A plan: while it waits for approval, one card ("Approve 5 image generations", its numbered steps, and the bar to say
// what to change, stop, or generate them all), in the dock above the message box; once approved, what it made; turned
// down, a folded "Cancelled".

import { CreditMark, Icon } from '../../../common/components/Icon/Icon';
import { cx } from '../../../common/cx';
import { approve, revise, storyboard } from './actions';
import type { AgentChat } from './chat';
import { Fold } from './Fold';
import { PlanStep } from './PlanStep';
import { allMade, checking } from './checks';
import { AnimateBar, readyToAnimate } from './Storyboard';
import { eligible, flagged, planCount } from './shots';
import { Results } from './Takes';
import type { Run } from './types';
import s from './Plan.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
const css = classesOf(css0, css1);

/** The newest plan that waits for approval: its bar goes in the dock. */
export const docked = (chat: AgentChat) => [...chat.runs].reverse().find((r) => r.state === 'proposed') || null;

/** They are asked about once, for the newest turn, when every shot of its plan is made and checked. */
export const retakeOpen = (chat: AgentChat, run: Run | undefined) =>
  !!run &&
  chat.runs[chat.runs.length - 1] === run &&
  run.state === 'approved' &&
  !chat.pending &&
  !run.queuedAnswer &&
  allMade(chat, run) &&
  !checking(chat, run) &&
  flagged(run).length > 0;

function ApproveBar({ chat, run }: { chat: AgentChat; run: Run }) {
  const short = run.total > chat.credits;
  const note = run.ui.note || '';
  const several = run.steps.filter((x) => !x.skipped).length > 1;
  return (
    <div className={s['agent-approve']}>
      <input
        type="text"
        className={s['approve-note']}
        placeholder={
          short
            ? `Needs ${run.total} credits, you have ${chat.credits}. Or say what to change…`
            : 'Type something else…'
        }
        aria-label="What to change in this plan"
        value={note}
        onChange={(e) => chat.patch(run.ui, { note: e.target.value })}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
            e.preventDefault();
            revise(chat, run);
          }
        }}
      />
      <span className="row">
        {eligible(run).length > 3 && (
          <button
            className="btn small quiet"
            disabled={chat.working || chat.busy || chat.boarding}
            title="Draw a cheap still for each shot first; animate the ones you keep"
            onClick={() => void storyboard(chat, run)}
          >
            Storyboard first
          </button>
        )}
        <button
          className="btn small quiet"
          title="Turn the plan down (Esc)"
          onClick={() => chat.patch(run, { state: 'dismissed' }, true)}
        >
          Stop
          <kbd className={s['esc-key']}>esc</kbd>
        </button>
        <button
          className={cx('btn small primary', !note && 'hidden')}
          disabled={chat.busy || chat.working}
          onClick={() => revise(chat, run)}
        >
          Send change
        </button>
        <button
          className={cx('btn small', s['approval-go'], !!note && 'hidden')}
          disabled={chat.working || short || run.steps.every((x) => x.skipped)}
          title={`You have ${chat.credits} credits`}
          onClick={() => void approve(chat, run)}
        >
          {several ? 'Generate all' : 'Generate'}
          <span className={s['approval-price']}>
            · {String(run.total)}
            <CreditMark label="credits" />
          </span>
        </button>
      </span>
    </div>
  );
}

export function ApprovalCard({ chat, run }: { chat: AgentChat; run: Run }) {
  const kind = planCount(run, true);
  const n = run.steps.filter((x) => !x.skipped).length;
  const what = kind ? `${kind} ${n === 1 ? 'generation' : 'generations'}` : n === 1 ? 'generation' : 'generations';
  const folded = !!run.ui.folded;
  return (
    <div className={cx(s.approval, folded && s.folded)}>
      <button
        type="button"
        className={s['approval-head']}
        aria-expanded={!folded}
        onClick={() => chat.patch(run.ui, { folded: !folded })}
      >
        <Icon name={kind === 'image' ? 'image' : kind === 'sound' ? 'audio' : 'film'} />
        <b>{`Approve ${n} ${what}`}</b>
        <span className={cx(s['approval-chevron'], folded && s.flip)}>
          <Icon name="down" />
        </span>
      </button>
      {!folded && run.contentNote && (
        <p className="notice small" role="note">
          {run.contentNote}
        </p>
      )}
      {!folded && (
        <div className={s['agent-dock-steps']}>
          <ol className={s['approval-list']}>
            {run.steps.map((step, i) => (
              <PlanStep key={i} chat={chat} run={run} step={step} />
            ))}
          </ol>
        </div>
      )}
      <ApproveBar chat={chat} run={run} />
    </div>
  );
}

function Waiting({ words }: { words: string }) {
  return (
    <div className={s['turn-asking']}>
      <span className={s['turn-asking-dot']} aria-hidden="true" />
      <span>{words}</span>
    </div>
  );
}
export { Waiting };

export function PlanView({ chat, run }: { chat: AgentChat; run: Run }) {
  if (run.state === 'dismissed')
    return (
      <Fold
        chat={chat}
        glyph="film"
        title="Generation"
        sub={run.revised ? 'Changed' : 'Cancelled'}
        state={chat.stateOf(run, 'cancelled', () => ({}))}
        className="cancelled"
        body={
          <ol className={s['approval-list']}>
            {run.steps.map((step, i) => (
              <PlanStep key={i} chat={chat} run={run} step={step} />
            ))}
          </ol>
        }
      />
    );
  if (run.state === 'proposed') {
    // The newest plan waiting for approval is in the dock; the conversation only says it waits. An older one stays here.
    if (run === docked(chat)) return <Waiting words={'Waiting for your approval · ' + planCount(run)} />;
    return (
      <div className={cx(s['agent-plan'], s['approval-card'])}>
        <ApprovalCard chat={chat} run={run} />
      </div>
    );
  }
  const waiting = retakeOpen(chat, run) ? flagged(run).length : 0;
  return (
    <div className={s['agent-plan']}>
      <Results chat={chat} run={run} />
      {readyToAnimate(chat, run) && !chat.working && <AnimateBar chat={chat} run={run} />}
      {/* what the check found is in the dock above the message box; the conversation only says it waits */}
      {waiting > 0 && (
        <Waiting words={`Waiting for your choice · ${waiting} ${waiting === 1 ? 'shot' : 'shots'} could be closer`} />
      )}
      {/* an approved plan with steps still to carry out: it was interrupted, or a step failed */}
      {run.state === 'approved' &&
        !chat.working &&
        run.steps.some((step) => !step.job && !step.made && !step.skipped) && (
          <div className={s['agent-approve']}>
            <span className={css('slate-text')}>Not every step was carried out.</span>
            <button className="btn small primary" onClick={() => void approve(chat, run)}>
              Resume
            </button>
          </div>
        )}
    </div>
  );
}
