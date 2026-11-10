// What an approved plan made: its results in the order of its steps, pictures that follow one another in a grid and
// clips too. Failed shots can be tried again, finished ones rolled again; with more than one take, the one that goes on
// is chosen.

import { Icon } from '../../../common/components/Icon/Icon';
import { Still } from '../../../common/components/Still';
import { cx } from '../../../common/cx';
import { approve } from './actions';
import type { AgentChat } from './chat';
import { Fold } from './Fold';
import { Tags } from './PlanStep';
import { Grid } from './ResultGrid';
import { CheckLine, ReviewNote } from './Review';
import { takesOf } from './shots';
import { Foot, Head, Keyframes, ResultMedia, RollBar, TakePick, progressOf } from './TakeParts';
import type { Run, Step } from './types';
import s from './Results.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared3.module.css';
const css = classesOf(css0);

const KIND_NAMES: Record<string, string> = { video: 'Video', image: 'Image', audio: 'Audio' };

/** The prompt, the references and the settings a step was made with, folded under "Generation information". */
function Information({ chat, step }: { chat: AgentChat; step: Step }) {
  const references = [
    ...(step.uses || []).map((use) => ({
      url: use.asset ? `/api/kit/${use.asset}/file` : `/api/library/${use.id}/file`,
      kind: use.kind || 'image',
      name: use.name,
    })),
    ...(step.start ? [{ url: `/api/library/${step.start.id}/file`, kind: 'image', name: step.start.name }] : []),
  ];
  const label = step.open ? 'Show less' : 'Show the whole prompt';
  return (
    <Fold
      chat={chat}
      glyph="film"
      title="Generation"
      sub="information"
      state={step.info ?? {}}
      className="info"
      stretch
      body={
        <>
          {step.prompt && (
            <div className={s['agent-prompt']}>
              <p className={cx('small muted', !step.open && s.clamp)}>{step.prompt}</p>
              <span className={s['agent-prompt-tools']}>
                <button
                  type="button"
                  className="icon-btn small"
                  title={label}
                  aria-label={label}
                  onClick={() => chat.patch(step, { open: !step.open })}
                >
                  <Icon name="expand" />
                </button>
              </span>
            </div>
          )}
          {references.length > 0 && (
            <div className={s['info-refs']}>
              {references.map((r, i) => (
                <span key={i} className={s['info-ref']} title={r.name}>
                  <Still url={r.url} kind={r.kind} name={r.name} />
                </span>
              ))}
            </div>
          )}
          <Tags step={step} />
          {step.why && <div className={s['step-why']}>{step.why}</div>}
        </>
      }
    />
  );
}

function ResultBlock({ chat, run, step }: { chat: AgentChat; run: Run; step: Step }) {
  const p = progressOf(chat, step, step);
  const kind = step.kind === 'image' || step.kind === 'audio' ? step.kind : 'video';
  step.info ??= {};
  return (
    <section className={s.result}>
      <Head
        state={p.state}
        name={KIND_NAMES[kind]}
        done={p.state === 'done' ? 1 : 0}
        of={1}
        model={step.workflow_title || step.name}
      />
      <Information chat={chat} step={step} />
      <div className={s['result-name']}>{step.name}</div>
      <ResultMedia chat={chat} take={step} step={step} />
      {/* a job that failed or was cancelled gave its credits back: the step can be queued again as it was */}
      {p.state === 'failed' && step.job && !chat.working && (
        <div className="row">
          <button
            className="btn small"
            onClick={() => {
              chat.patch(step, { job: null, queuedAt: null, error: null });
              void approve(chat, run);
            }}
          >
            Try again
          </button>
          <span className={css('slate-text')}>{`${step.credits || 0} cr`}</span>
        </div>
      )}
      <Keyframes chat={chat} take={step} step={step} />
      <Foot chat={chat} take={step} />
      <CheckLine chat={chat} run={run} steps={[step]} />
      <ReviewNote step={step} />
      <RollBar chat={chat} run={run} step={step} />
      {takesOf(step)
        .slice(1)
        .map((t, i) => (
          <div key={i} className={s.retake}>
            <div className={s['result-name']}>{`Take ${i + 2}: ${step.name}`}</div>
            <ResultMedia chat={chat} take={t} step={step} />
            <Keyframes chat={chat} take={t} step={step} />
            <Foot chat={chat} take={t} />
          </div>
        ))}
      <TakePick chat={chat} step={step} />
    </section>
  );
}

/** What a plan made, in the order of its steps; generated pictures that follow one another share a grid, clips too. */
export function Results({ chat, run }: { chat: AgentChat; run: Run }) {
  type Block = Step | { kind: 'image' | 'video'; steps: Step[] };
  const blocks: Block[] = [];
  let grid: { kind: 'image' | 'video'; steps: Step[] } | null = null;
  for (const step of run.steps) {
    if (step.skipped) continue;
    const kind = step.settings && (step.kind === 'image' || step.kind === 'video') ? step.kind : null;
    if (kind && grid && grid.kind === kind) grid.steps.push(step);
    else if (kind) {
      grid = { kind, steps: [step] };
      blocks.push(grid);
    } else {
      grid = null;
      blocks.push(step);
    }
  }
  return (
    <div className={s.results}>
      {blocks.map((b, i) =>
        !('steps' in b) ? (
          <ResultBlock key={i} chat={chat} run={run} step={b} />
        ) : b.kind === 'image' || b.steps.length > 1 ? (
          <Grid key={i} chat={chat} run={run} steps={b.steps} kind={b.kind} />
        ) : (
          // a single clip keeps its full block (larger, with its frames, Roll again and the check in line)
          <ResultBlock key={i} chat={chat} run={run} step={b.steps[0]} />
        ),
      )}
    </div>
  );
}
