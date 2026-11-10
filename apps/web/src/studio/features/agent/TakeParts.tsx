// The pieces of a result: where it stands, its picture, its frames, its thumbs, where it is on the canvas, Roll again,
// and which take goes on.

import { useState } from 'react';
import { oneItem } from '@scene/shared/api/items';
import { Icon } from '../../../common/components/Icon/Icon';
import { Reel } from '../../../common/components/Film/Film';
import { cx } from '../../../common/cx';
import { phaseOf } from '../../../common/format';
import { openViewer } from '../../../common/media/Viewer';
import type { Item } from '../../../common/media/item';
import { rate, reroll } from './actions';
import type { AgentChat } from './chat';
import { retake } from './checks';
import { SoundPlayer } from './SoundPlayer';
import { clock, takesOf, usedTake } from './shots';
import type { Run, Step, Take } from './types';
import s from './Results.module.css';

type Progress = { state: string; text: string; share?: number };

/** Where a step is: made, being made, waiting, failed, or not started. */
export function progressOf(chat: AgentChat, take: Take, step: Step): Progress {
  if (take.made) return { state: 'done', text: 'Done' };
  if (take.error && !take.job) return { state: 'failed', text: 'Not made: ' + take.error };
  const job = chat.jobOf(take.job);
  if (job) {
    if (job.status === 'running') {
      const share = job.steps ? (Math.max(job.clip, 1) - 1 + job.step / job.steps) / Math.max(job.clips, 1) : 0;
      return { state: 'running', share, text: job.steps ? phaseOf(share) : 'Setting up the shot' };
    }
    if (job.status === 'queued')
      return { state: 'queued', text: job.position ? `Waiting · ${job.position} in the queue` : 'Waiting' };
    if (job.status === 'failed') return { state: 'failed', text: 'Failed. The credits came back.' };
    if (job.status === 'cancelled') return { state: 'failed', text: 'Cancelled. The credits came back.' };
  }
  if (take.job) return { state: 'running', share: 1, text: 'Finishing' };
  if (step.waiting)
    return { state: 'queued', text: step.after ? `Waits for step ${step.after.step + 1}` : 'Waits for the shots' };
  return { state: 'queued', text: 'Not started' };
}

/** The shape a result will have, so its place does not jump when it arrives. */
const shapeOf = (take: Take, step: Step): [number, number] => {
  const made = take.madeInfo || {};
  return made.width && made.height ? [made.width, made.height] : step.shape || [16, 9];
};
export const aspect = (take: Take, step: Step) => {
  const [w, h] = shapeOf(take, step);
  return { aspectRatio: `${w} / ${h}` };
};
const RESULT_HEIGHT = 200; // a result on its own is at most this tall: a portrait clip is not stretched across the panel
const sized = (take: Take, step: Step) => {
  const [w, h] = shapeOf(take, step);
  return { aspectRatio: `${w} / ${h}`, width: `min(100%, ${Math.round((RESULT_HEIGHT * w) / h)}px)` };
};
export const secondsOf = (take: Take, step: Step) =>
  take.madeInfo?.duration || (step.current?.duration || 5) * (step.settings?.clips || 1);

export async function openLarge(id: number | null | undefined) {
  try {
    if (id) openViewer(await oneItem<Item>(id), { actions: [] });
  } catch {
    // nothing to open
  }
}

export function ResultMedia({ chat, take, step }: { chat: AgentChat; take: Take; step: Step }) {
  const p = progressOf(chat, take, step);
  if (p.state !== 'done') {
    return (
      <div
        className={cx(s['result-wait'], s[p.state])}
        style={step.kind === 'audio' || p.state === 'failed' ? undefined : sized(take, step)}
      >
        <div className={s['result-wait-inner']}>
          {p.state === 'running' && <Reel share={p.share ?? 0} count={18} />}
          <span>{p.text}</span>
        </div>
      </div>
    );
  }
  const id = take.made as number;
  if (step.kind === 'audio')
    return (
      <div className={s['result-audio']}>
        <SoundPlayer url={`/api/library/${id}/file`} name={step.name} />
      </div>
    );
  const video = step.kind !== 'image';
  const seconds = video && (take.madeInfo?.duration || step.current?.duration);
  return (
    <button
      type="button"
      className={s['result-media']}
      title="Show it on the canvas"
      style={sized(take, step)}
      onClick={() => chat.env.onFocus(id)}
    >
      <img src={`/api/library/${id}/poster`} alt={step.name} loading="lazy" />
      {video && (
        <span className={s['clip-badge']}>
          <Icon name="play" />
          {seconds ? `${Math.round(seconds)}s` : 'Video'}
        </span>
      )}
    </button>
  );
}

/** One frame of a clip: a click shows the clip on the canvas; a frame that can't be had goes. */
export function Keyframe({ chat, id, at }: { chat: AgentChat; id: number; at: number }) {
  const [gone, setGone] = useState(false);
  if (gone) return null;
  return (
    <button
      type="button"
      className={s.keyframe}
      title={`At ${clock(at)}: show the clip on the canvas`}
      onClick={() => chat.env.onFocus(id)}
    >
      <img src={`/api/library/${id}/frame?at=${at}`} alt="" loading="lazy" onError={() => setGone(true)} />
      <span>{clock(at)}</span>
    </button>
  );
}

export function Keyframes({ chat, take, step }: { chat: AgentChat; take: Take; step: Step }) {
  if (!take.made || step.kind !== 'video') return null;
  const seconds = secondsOf(take, step);
  const times = [...new Set([0, seconds / 2, Math.max(0, seconds - 0.2)].map((t) => Math.round(t * 10) / 10))];
  return (
    <div className={s.keyframes}>
      {times.map((t) => (
        <Keyframe key={t} chat={chat} id={take.made as number} at={t} />
      ))}
    </div>
  );
}

export function Rating({ chat, take }: { chat: AgentChat; take: Take }) {
  const rated = take.rating ?? 0;
  return (
    <span className={s.rate}>
      <button
        type="button"
        className={cx('icon-btn small', rated > 0 && s.on)}
        aria-pressed={rated > 0}
        title="Good: the agent will reuse it"
        aria-label="Thumbs up"
        onClick={() => void rate(chat, take, 1)}
      >
        <Icon name="thumbup" />
      </button>
      <button
        type="button"
        className={cx('icon-btn small', rated < 0 && s.on, rated < 0 && s.bad)}
        aria-pressed={rated < 0}
        title="Not good: the agent will not use it"
        aria-label="Thumbs down"
        onClick={() => void rate(chat, take, -1)}
      >
        <Icon name="thumbdown" />
      </button>
    </span>
  );
}

/** Where the result is on the canvas: "Shot 3 › Take 2", which takes you there. */
function Crumb({ chat, take }: { chat: AgentChat; take: Take }) {
  const where = chat.env.locate(take.made as number);
  return (
    <button
      type="button"
      className={s.crumb}
      title="Show it on the canvas"
      onClick={() => chat.env.onFocus(take.made as number)}
    >
      <Icon name={where ? 'branch' : 'target'} />
      {where ? `${where.shot} › Take ${where.take}` : 'Show on canvas'}
    </button>
  );
}

export function Foot({ chat, take }: { chat: AgentChat; take: Take }) {
  if (!take.made) return null;
  return (
    <div className={s['result-foot']}>
      <Crumb chat={chat} take={take} />
      <span style={{ flex: 1 }} />
      <Rating chat={chat} take={take} />
    </div>
  );
}

export function RollBar({ chat, run, step }: { chat: AgentChat; run: Run; step: Step }) {
  if (!step.made || !step.settings || step.take2 || chat.working || step.kind === 'audio') return null;
  const plan = step.rolling;
  if (plan)
    return (
      <div className="row">
        <button
          className="btn small primary"
          disabled={plan.credits > chat.credits}
          onClick={() => {
            chat.patch(step, { retake: plan, rolling: null });
            void retake(chat, run, step);
          }}
        >
          {`Make take 2 · ${plan.credits} cr`}
        </button>
        <button className="btn small quiet" onClick={() => chat.patch(step, { rolling: null })}>
          Cancel
        </button>
      </div>
    );
  return (
    <div className="row">
      <button
        className="btn small quiet"
        disabled={step.rollBusy}
        title="Make this shot again with a new seed"
        onClick={() => void reroll(chat, step)}
      >
        <Icon name="retry" />
        {step.rollBusy ? 'Pricing…' : 'Roll again'}
      </button>
      {step.rollError && <span className="small error">{step.rollError}</span>}
    </div>
  );
}

/** Which take of a shot goes on, once there is more than one made. */
export function TakePick({ chat, step }: { chat: AgentChat; step: Step }) {
  const all = takesOf(step);
  if (all.filter((t) => t.made).length < 2) return null;
  const now = all.indexOf(usedTake(step)) + 1;
  return (
    <div className={cx('row', s['take-pick'])}>
      <span className="small muted">Goes on with:</span>
      {all.map(
        (t, i) =>
          t.made && (
            <button
              key={i}
              className={cx('btn small', now === i + 1 ? 'primary' : 'quiet')}
              onClick={() => chat.patch(step, { chosen: i + 1 }, true)}
            >
              {'Take ' + (i + 1)}
            </button>
          ),
      )}
    </div>
  );
}

export function Head({
  state,
  name,
  done,
  of,
  model,
}: {
  state: string;
  name: string;
  done: number;
  of: number;
  model: string;
}) {
  return (
    <div className={s['result-head']}>
      <i className={cx(s['dot-state'], s[state])} />
      <b>{name}</b>
      <span className="muted">{`· ${done}/${of}`}</span>
      {model && <span className={s['result-model']}>{model}</span>}
    </div>
  );
}
