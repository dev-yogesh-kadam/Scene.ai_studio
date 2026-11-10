// Pictures made by the steps of one plan, side by side, and clips too: each opens on the canvas, ⓘ shows how it was made,
// ⤢ opens it large; a clip shows its first and last frame under it. What a shot still needs is listed under the grid.

import { Icon } from '../../../common/components/Icon/Icon';
import { Reel } from '../../../common/components/Film/Film';
import { popover } from '../../../common/components/Popover';
import { cx } from '../../../common/cx';
import type { AgentChat } from './chat';
import { Tags } from './PlanStep';
import { CheckLine, ReviewNote } from './Review';
import { reviewShown, usedTake } from './shots';
import { Head, Keyframe, Rating, RollBar, TakePick, aspect, openLarge, progressOf, secondsOf } from './TakeParts';
import type { Run, Step, Take } from './types';
import s from './ResultGrid.module.css';

/** ⓘ on a tile: how it was made. */
function InfoButton({ chat, run, step, roll }: { chat: AgentChat; run: Run; step: Step; roll: boolean }) {
  return (
    <button
      type="button"
      className={cx(s['tile-btn'], s.info)}
      title="How it was made"
      aria-label="How it was made"
      onClick={(e) =>
        popover(
          e.currentTarget,
          () => (
            <>
              <b>{step.name}</b>
              <p className="small muted">{step.prompt}</p>
              <Tags step={step} />
              {roll && step.why && <div className={s['step-why']}>{step.why}</div>}
              {roll && <RollBar chat={chat} run={run} step={step} />}
            </>
          ),
          s['pop-info'],
        )
      }
    >
      <Icon name="info" />
    </button>
  );
}

const stateOfAll = (states: string[], done: number) =>
  done === states.length
    ? 'done'
    : states.includes('running')
      ? 'running'
      : states.includes('failed')
        ? 'failed'
        : 'queued';

function Tile({ chat, run, step, take, video }: { chat: AgentChat; run: Run; step: Step; take: Take; video: boolean }) {
  const p = progressOf(chat, take, step);
  if (p.state !== 'done')
    return (
      <div className={cx(s['res-tile'], s.wait, s[p.state])} style={aspect(take, step)}>
        {p.state === 'running' && <Reel share={p.share ?? 0} count={18} />}
        <span>{p.text}</span>
      </div>
    );
  const id = take.made as number;
  return (
    <div className={s['res-tile']} style={aspect(take, step)}>
      <button
        type="button"
        className={s['tile-media']}
        title={`${step.name}: show it on the canvas`}
        onClick={() => chat.env.onFocus(id)}
      >
        <img src={`/api/library/${id}/poster`} alt={step.name} loading="lazy" />
      </button>
      {video && (
        <span className={s['clip-badge']}>
          <Icon name="play" />
          {`${Math.round(secondsOf(take, step))}s`}
        </span>
      )}
      <InfoButton chat={chat} run={run} step={step} roll={video} />
      <button
        type="button"
        className={cx(s['tile-btn'], s.open)}
        title="Open it large"
        aria-label="Open it large"
        onClick={() => void openLarge(id)}
      >
        <Icon name="expand" />
      </button>
      <span className={s['tile-rate']}>
        <Rating chat={chat} take={take} />
      </span>
    </div>
  );
}

export function Grid({
  chat,
  run,
  steps,
  kind,
}: {
  chat: AgentChat;
  run: Run;
  steps: Step[];
  kind: 'image' | 'video';
}) {
  const video = kind === 'video';
  const takes = steps.map((x) => (video ? usedTake(x) : x));
  const done = takes.filter((t) => t.made).length;
  const states = steps.map((x, i) => progressOf(chat, takes[i], x).state);
  const models = [...new Set(steps.map((x) => x.workflow_title).filter(Boolean))].join(', ');
  const ends = (take: Take, step: Step) => {
    const t = secondsOf(take, step);
    return [...new Set([0, Math.max(0, t - 0.2)].map((x) => Math.round(x * 10) / 10))];
  };
  return (
    <section className={s.result}>
      <Head
        state={stateOfAll(states, done)}
        name={video ? 'Video' : 'Image'}
        done={done}
        of={steps.length}
        model={models}
      />
      <div className={video ? s['clip-grid'] : cx(s['result-grid'], steps.length === 1 && s.one)}>
        {steps.map((step, i) =>
          video ? (
            <div key={i} className={s['clip-cell']}>
              <Tile chat={chat} run={run} step={step} take={takes[i]} video />
              {takes[i].made && (
                <div className={s['clip-ends']}>
                  {ends(takes[i], step).map((t) => (
                    <Keyframe key={t} chat={chat} id={takes[i].made as number} at={t} />
                  ))}
                </div>
              )}
            </div>
          ) : (
            <Tile key={i} chat={chat} run={run} step={step} take={step} video={false} />
          ),
        )}
      </div>
      {/* one line while the plan's shots are checked; then what a shot still needs */}
      <CheckLine chat={chat} run={run} steps={steps} />
      {steps
        .filter((x) => reviewShown(x) || (video && (x.rolling || x.rollBusy || x.rollError)))
        .map((x, i) => (
          <div key={i} className={s['grid-review']}>
            <b>{x.name}</b>
            <ReviewNote step={x} />
            {video && (x.rolling || x.rollBusy || x.rollError) && <RollBar chat={chat} run={run} step={x} />}
            <TakePick chat={chat} step={x} />
          </div>
        ))}
    </section>
  );
}
