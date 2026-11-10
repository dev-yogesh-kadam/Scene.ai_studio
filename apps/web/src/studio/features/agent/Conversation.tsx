// The log of a conversation: its turns, the one being answered, or for a new conversation a welcome with a few ways to
// start. It goes to its end when something new arrives; opening a fold or changing a setting leaves it where it is.

import { useLayoutEffect, useRef, useState } from 'react';
import { Icon } from '../../../common/components/Icon/Icon';
import { cx } from '../../../common/cx';
import type { AgentChat } from './chat';
import { LiveTurn } from './LiveTurn';
import { Message } from './Message';
import s from './Conversation.module.css';

const STARTERS = [
  'A 6 second shot of a fox crossing a snowy road at dawn',
  'A product shot of a perfume bottle turning on black glass',
  'Continue the selected shot for 5 more seconds',
  'Plan a 3 shot ad for a coffee shop, portrait for Reels',
];

export function Conversation({ chat, onStarter }: { chat: AgentChat; onStarter: (text: string) => void }) {
  const log = useRef<HTMLDivElement>(null);
  const atEnd = useRef(true);
  const [far, setFar] = useState(false); // scrolled up: a button to the newest message
  const seen = useRef(chat.follow);
  useLayoutEffect(() => {
    const node = log.current;
    if (!node) return;
    const follow = seen.current !== chat.follow;
    seen.current = chat.follow;
    if (follow || (chat.pending && atEnd.current)) node.scrollTop = node.scrollHeight;
  });
  const empty = !chat.runs.length && !chat.pending;
  return (
    <div className={s['agent-log-wrap']}>
      <div
        ref={log}
        className={s['agent-log']}
        onScroll={(e) => {
          const n = e.currentTarget;
          const left = n.scrollHeight - n.scrollTop - n.clientHeight;
          atEnd.current = left < 48;
          setFar(left >= 160);
        }}
      >
        {empty ? (
          <div className={s['agent-welcome']}>
            <h2>What are we making?</h2>
            <p className="muted">
              Describe a shot, press + to attach a file, or start from one of these. Nothing runs until you approve.
            </p>
            <div className={s['agent-starters']}>
              {STARTERS.map((text) => (
                <button key={text} type="button" className={s['agent-starter']} onClick={() => onStarter(text)}>
                  {text}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {chat.runs.map((run) => (
              <Message key={run.at} chat={chat} run={run} />
            ))}
            {chat.pending && <LiveTurn chat={chat} pending={chat.pending} />}
          </>
        )}
      </div>
      <button
        type="button"
        className={cx(s['agent-to-end'], !far && 'hidden')}
        title="Go to the newest"
        aria-label="Go to the newest message"
        onClick={() => log.current?.scrollTo({ top: log.current.scrollHeight, behavior: 'smooth' })}
      >
        <Icon name="down" />
      </button>
    </div>
  );
}
