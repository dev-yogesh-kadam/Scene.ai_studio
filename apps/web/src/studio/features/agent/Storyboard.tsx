// Under the stills of a storyboard once they are drawn: tap one to leave it out, then animate the rest.

import { cx } from '../../../common/cx';
import { animate } from './actions';
import type { AgentChat } from './chat';
import { progressOf } from './TakeParts';
import { usedTake } from './shots';
import type { Run } from './types';
import s from './Storyboard.module.css';

export function readyToAnimate(chat: AgentChat, run: Run) {
  const stills = run.steps.filter((x) => x.stage === 'still' && !x.skipped);
  return (
    stills.length > 0 &&
    !run.animated &&
    stills.every((x) => x.made || progressOf(chat, x, x).state === 'failed') &&
    stills.some((x) => x.made)
  );
}

export function AnimateBar({ chat, run }: { chat: AgentChat; run: Run }) {
  const stills = run.steps.filter((x) => x.stage === 'still' && x.made);
  const chosen = stills.filter((x) => !x.out);
  return (
    <div className={s['agent-animate']}>
      <div className="small muted">The stills are ready. Tap one to leave it out, then animate the rest.</div>
      <div className={s['animate-tiles']}>
        {stills.map((x, i) => (
          <button
            key={i}
            type="button"
            className={cx(s['animate-tile'], x.out && s.out)}
            title={x.name + (x.out ? ' (left out)' : '')}
            onClick={() => chat.patch(x, { out: !x.out }, true)}
          >
            <img src={`/api/library/${usedTake(x).made}/poster`} alt={x.name} loading="lazy" />
            <span>{x.name.replace(/^Still · /, '')}</span>
          </button>
        ))}
      </div>
      <div className="row">
        <span style={{ flex: 1 }} />
        <button
          className="btn small primary"
          disabled={!chosen.length || chat.busy || chat.working || chat.boarding}
          onClick={() => void animate(chat, run)}
        >
          {`Animate ${chosen.length} ${chosen.length === 1 ? 'shot' : 'shots'}`}
        </button>
      </div>
    </div>
  );
}
