// The turn being answered: the message, the agent's work as it happens, and what it is doing now.

import { useEffect, useRef, useState } from 'react';
import { cx } from '../../../common/cx';
import { reducedMotion } from '../../../common/hooks/useAppearance';
import type { AgentChat } from './chat';
import { WorkRows } from './Fold';
import { Said, usePick } from './Message';
import { span } from './shots';
import type { Pending } from './types';
import f from './Fold.module.css';
import s from './Message.module.css';

// Feel-good words shown under the dots while the agent is just thinking, shuffled every few seconds.
const WHIMSY = [
  'Imagining…',
  'Daydreaming…',
  'Dreaming up shots…',
  'Sketching ideas…',
  'Chasing the muse…',
  'Brewing something good…',
  'Framing the scene…',
  'Finding the light…',
  'Scribbling storyboards…',
  'Picturing it…',
  'Warming up the lens…',
  'Mixing a little magic…',
  'Letting it marinate…',
  'Rolling the reels…',
  'Casting the shot…',
  'Painting with pixels…',
  'Humming a tune…',
  'Tuning the vibe…',
  'Thinking happy thoughts…',
  'Connecting the dots…',
  'Setting the stage…',
  'Reading the script twice…',
  'Counting the frames…',
  'Asking the cast nicely…',
  'Polishing the clapperboard…',
  'Checking the continuity…',
  'Feeding the gaffer…',
  'Rehearsing the lines…',
  'Bribing the lighting crew…',
  'Untangling the cables…',
  'Finding the best angle…',
  'Waiting for golden hour…',
  'Cueing the boom mic…',
  'Measuring the dolly track…',
  'Steadying the shot…',
  'Calling places…',
  'Pouring the director a coffee…',
  'Sharpening the focus…',
  'Lining up the next take…',
  'Reading the room…',
  'Syncing the slate…',
];

/** The turn being answered: the message, the agent's work as it happens, and what it is doing now. Only a row that is
 *  new fades in; the clock and the word change their text, so nothing blinks. */
export function LiveTurn({ chat, pending }: { chat: AgentChat; pending: Pending }) {
  const onPick = usePick(chat);
  const [now, setNow] = useState(() => Date.now());
  const [whimsy, setWhimsy] = useState(() => Math.floor(Math.random() * WHIMSY.length));
  useEffect(() => {
    const clock = setInterval(() => setNow(Date.now()), 1000);
    const words = setInterval(() => setWhimsy((n) => n + 1), 2600);
    return () => {
      clearInterval(clock);
      clearInterval(words);
    };
  }, []);
  const rows = pending.events.filter((e) => e.type === 'thought' || (e.type === 'activity' && e.icon !== 'info'));
  const [first] = useState(rows.length); // what was there when the turn was drawn does not fade in
  // A real phase the server named wins over the feel-good words.
  const word = (
    pending.status && !/^(thinking|working)/i.test(pending.status) ? pending.status : WHIMSY[whimsy % WHIMSY.length]
  ).replace(/…$/, '');
  const say = useRef<HTMLSpanElement>(null);
  const seen = useRef(word);
  useEffect(() => {
    if (seen.current === word) return;
    seen.current = word;
    // the new word rises in; the shimmer on it keeps running
    if (!reducedMotion())
      say.current?.animate([{ opacity: 0, transform: 'translateY(4px)' }, {}], {
        duration: 350,
        easing: 'cubic-bezier(.2,.8,.2,1)',
      });
  }, [word]);
  return (
    <div className={cx(s.turn, s.live)} data-live>
      <Said chat={chat} run={pending} onPick={onPick} />
      <div className={cx(f.fold, f.work, f.open, !rows.length && 'hidden')}>
        <div className={f['fold-head']}>
          <span className={f['live-spinner']} aria-hidden="true" />
          <span className={f['fold-title']}>Working</span>
          <span className={f['fold-sub']}>{span((now - pending.started) / 1000)}</span>
        </div>
        <div className={f['fold-body']}>
          <WorkRows chat={chat} entries={rows} states={{}} newFrom={first} />
        </div>
      </div>
      <div className={s['agent-thinking']} role="status" aria-live="polite">
        <span className={s['thinking-dots']} aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <span ref={say} className={s['thinking-say']}>
          <span className={s['thinking-word']}>{word}</span>
        </span>
      </div>
    </div>
  );
}
