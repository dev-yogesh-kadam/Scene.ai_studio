// One conversation in the panel: the log, the dock above the message box (the newest plan waiting for approval, the
// questions of the newest turn, or what the check of the newest plan found), and the box. Esc stops a reply or turns
// down the plan that waits.

import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import { cx } from '../../../common/cx';
import type { Item } from '../../../common/media/item';
import { Composer, type ComposerHandle } from './Composer';
import { Conversation } from './Conversation';
import { askOpen } from './Message';
import { ApprovalCard, docked, retakeOpen } from './PlanView';
import { AskCard, RetakeCard } from './Review';
import type { ConversationProps } from './useConversation';
import { useConversation } from './useConversation';
import s from './Conversation.module.css';

export type PanelHandle = { attach: (item: Item) => void; focus: () => void };

type Props = ConversationProps & {
  hidden: boolean;
  selectionNow: Item[];
  pick: ((onPick: (items: Item[]) => void) => void) | null;
};

export const AgentPanel = forwardRef<PanelHandle, Props>(function AgentPanel(
  { hidden, selectionNow, pick, ...props },
  ref,
) {
  const chat = useConversation(props);
  const composer = useRef<ComposerHandle>(null);
  const dock = useRef<HTMLDivElement>(null);
  useImperativeHandle(
    ref,
    () => ({
      attach: (item) => composer.current?.attach(item),
      focus: () => composer.current?.focus(),
    }),
    [],
  );
  const newest = chat.runs[chat.runs.length - 1];
  const run = chat.pending ? null : docked(chat);
  const ask = !run && askOpen(chat, newest) ? newest : null;
  const offer = !run && !ask && retakeOpen(chat, newest) ? newest : null;
  const key = run ? String(run.at) : ask ? 'ask:' + ask.at : offer ? 'retake:' + offer.at : '';
  // A plan's note, or a card, takes the focus when it first shows.
  useEffect(() => {
    if (!key || !dock.current) return;
    const wanted = (n: Element) => (key.includes(':') ? n.getAttribute('role') === 'group' : n.tagName === 'INPUT');
    ([...dock.current.getElementsByTagName('*')].find(wanted) as HTMLElement | undefined)?.focus({
      preventScroll: true,
    });
  }, [key]);
  return (
    <div
      className={cx(s['agent-panel'], hidden && 'hidden')}
      onKeyDown={(e) => {
        if (e.key !== 'Escape') return;
        if (chat.pending) chat.pending.stop();
        else {
          const waiting = docked(chat);
          if (waiting && !chat.working) chat.patch(waiting, { state: 'dismissed' }, true);
        }
      }}
    >
      <Conversation chat={chat} onStarter={(text) => composer.current?.setText(text)} />
      <div ref={dock} className={cx(s['agent-dock'], !key && 'hidden', key && s.asking)} data-dock>
        {run ? (
          <ApprovalCard chat={chat} run={run} />
        ) : ask ? (
          <AskCard key={ask.at} chat={chat} run={ask} />
        ) : offer ? (
          <RetakeCard chat={chat} run={offer} />
        ) : null}
      </div>
      <Composer
        ref={composer}
        chat={chat}
        hidden={!!run || ((!!ask || !!offer) && !chat.generating())}
        selection={selectionNow}
        pick={pick}
      />
    </div>
  );
});
