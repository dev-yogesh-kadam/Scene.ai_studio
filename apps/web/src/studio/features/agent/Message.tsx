// One turn of the conversation: the message, what the agent did and thought, its reply, its questions, its plan, the
// work after approval, and what it cost. And the turn being answered, whose work comes in as it happens.

import { useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { openDialog } from '../../../common/components/Dialog';
import { CreditMark, Icon } from '../../../common/components/Icon/Icon';
import { cx } from '../../../common/cx';
import { compactContext } from './actions';
import type { AgentChat } from './chat';
import { Fold, WorkRows, glyphsOf } from './Fold';
import { Chip, Markdown, type OnPick } from './Markdown';
import { PlanView, Waiting } from './PlanView';
import { LONG_REPLY, questionsOf, span, spentBy } from './shots';
import type { Run, Spent } from './types';
import f from './Fold.module.css';
import s from './Message.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from './Message2.module.css';
const css = classesOf(css0, css1, css2);

const SPEND_KINDS: [keyof Spent, string][] = [
  ['video', 'Video'],
  ['image', 'Image'],
  ['audio', 'Audio'],
  ['llm', 'LLM'],
];

/** What was spent, by kind, beside (or above) what is pointed at. */
export function SpendCard({
  anchor,
  spent,
  above = false,
}: {
  anchor: HTMLElement;
  spent: Partial<Spent>;
  above?: boolean;
}) {
  const card = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const node = card.current;
    if (!node) return;
    const at = anchor.getBoundingClientRect();
    if (above) {
      node.style.top = Math.max(8, at.top - node.offsetHeight - 8) + 'px';
      node.style.left = Math.max(8, Math.min(at.left, window.innerWidth - node.offsetWidth - 8)) + 'px';
    } else {
      const right = at.right + 10 + node.offsetWidth < window.innerWidth;
      node.style.top = Math.max(8, at.top + at.height / 2 - node.offsetHeight / 2) + 'px';
      node.style.left = (right ? at.right + 10 : Math.max(8, at.left - node.offsetWidth - 10)) + 'px';
    }
  }, [anchor, above]);
  return createPortal(
    <div ref={card} className={s['agent-spend-card']} role="tooltip">
      {SPEND_KINDS.map(([k, label]) => (
        <div key={k} className={spent[k] ? '' : s.none}>
          <span>{label}</span>
          <b>{(spent[k] || 0) + ' cr'}</b>
        </div>
      ))}
    </div>,
    document.body,
  );
}

function TurnCost({ chat, run }: { chat: AgentChat; run: Run }) {
  const [over, setOver] = useState<HTMLElement | null>(null);
  const spent = spentBy([run], chat.jobs);
  if (!spent.total) return null;
  const show = (e: { currentTarget: HTMLElement }) => setOver(e.currentTarget);
  return (
    <span
      className={s['turn-cost']}
      tabIndex={0}
      aria-label={`This turn cost ${spent.total} credits`}
      onPointerEnter={show}
      onFocus={show}
      onPointerLeave={() => setOver(null)}
      onBlur={() => setOver(null)}
    >
      <CreditMark />
      {String(spent.total)}
      {over && <SpendCard anchor={over} spent={spent} above />}
    </span>
  );
}

/** A NeuralCore picture named in a reply, opened; an item goes to the canvas. */
export function usePick(chat: AgentChat): OnPick {
  return (table, id) => {
    if (table === 'item') return chat.env.onFocus(id);
    void openDialog(
      (close) => (
        <>
          <div className={css('asset-preview-media')}>
            <img src={`/api/kit/${id}/file`} alt="" />
          </div>
          <div className={css('asset-preview-words')}>
            <div className={css('dialog-buttons')}>
              <button className="btn small primary" onClick={() => close()}>
                Close
              </button>
            </div>
          </div>
        </>
      ),
      { className: css('asset-preview') },
    );
  };
}

// A run carried on by the studio once its steps were made: a note that it did, not a bubble as if the user wrote it.
const AUTO_SAID = /^Continue the run(?: \((\d+) steps? done\))?$/;

export function Said({
  chat,
  run,
  onPick,
}: {
  chat: AgentChat;
  run: Pick<Run, 'instruction' | 'parts' | 'auto'> & { ui?: Run['ui'] };
  onPick: OnPick;
}) {
  const words = String(run.instruction || '');
  if (run.auto || AUTO_SAID.test(words)) {
    const done = (words.match(AUTO_SAID) || [])[1];
    return (
      <div className={s['agent-auto']}>
        <Icon name="forward" />
        <span>
          {done ? `Carried on by itself · ${done} ${done === '1' ? 'step' : 'steps'} made` : 'Carried on by itself'}
        </span>
      </div>
    );
  }
  const parts = run.parts && run.parts.length ? run.parts : [{ text: run.instruction }];
  const length = parts.reduce((n, part) => n + (part.text || '').length, 0);
  const long = length > 320 || parts.reduce((n, part) => n + ((part.text || '').match(/\n/g) || []).length, 0) > 5;
  const more = !!run.ui?.saidMore;
  return (
    <div className={s['agent-said']} data-said>
      <p className={long && !more ? s.clamped : undefined}>
        {parts.map((part, i) =>
          part.id ? (
            <Chip
              key={i}
              table="item"
              id={part.id}
              known={{ name: part.name ?? '', kind: part.kind ?? 'image' }}
              onPick={onPick}
            />
          ) : (
            part.text
          ),
        )}
      </p>
      {long && run.ui && (
        <button
          type="button"
          className={s['more-btn']}
          onClick={() => chat.patch(run.ui as Run['ui'], { saidMore: !more })}
        >
          {more ? 'Show less' : 'Show more'}
          <span className={more ? s.flip : ''}>
            <Icon name="down" />
          </span>
        </button>
      )}
    </div>
  );
}

function Reply({ chat, run, onPick }: { chat: AgentChat; run: Run; onPick: OnPick }) {
  // The newest reply is shown in full; once a newer message is sent, a long one folds under Show more.
  const newest = run === chat.runs[chat.runs.length - 1] && !chat.pending;
  const long = !newest && (run.reply.length > LONG_REPLY || run.reply.split('\n').length > 10);
  const more = !!run.ui.more;
  return (
    <div className={cx(s['turn-reply'], run.error && 'error')}>
      <div className={cx(s.md, long && !more && s.clamped)}>
        <Markdown text={run.reply} chips={run.chips || {}} onPick={onPick} />
      </div>
      {long && (
        <button type="button" className={s['more-btn']} onClick={() => chat.patch(run.ui, { more: !more })}>
          {more ? 'Show less' : 'Show more'}
          <span className={more ? s.flip : ''}>
            <Icon name="down" />
          </span>
        </button>
      )}
      {(run.memoryUsed || []).length > 0 && (
        <div className={s['memory-used']} title="What the agent remembers of you, used for this answer">
          <Icon name="memory" />
          {(run.memoryUsed as string[]).map((key) => (
            <span key={key} className={cx(s['kit-flag'], s.soft)}>
              {key}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** A turn's questions wait for an answer while it is the newest turn and they were neither answered nor skipped. */
export const askOpen = (chat: AgentChat, run: Run | undefined) =>
  !!run &&
  chat.runs[chat.runs.length - 1] === run &&
  questionsOf(run).length > 0 &&
  !chat.pending &&
  !(run.question ? run.question.answer || run.question.skipped : run.questionsSent || run.questionsSkipped) &&
  !run.queuedAnswer;

/** In the conversation, a question stands as a record: what was asked and what was answered. */
function Asked({ chat, run }: { chat: AgentChat; run: Run }) {
  const list = questionsOf(run);
  const answers = run.question ? [run.question.answer] : run.picks || [];
  const skipped = run.question ? run.question.skipped : run.questionsSkipped;
  if (askOpen(chat, run))
    return <Waiting words={list.length > 1 ? `Asking ${list.length} questions` : 'Asking: ' + list[0].text} />;
  return (
    <div className={s['turn-question']}>
      {list.map((q, i) => (
        <div key={i} className={s['turn-question-row']}>
          <span className={s['turn-question-text']}>{(list.length > 1 ? `${i + 1}. ` : '') + q.text}</span>
          <span className={cx(s['turn-question-answer'], !answers[i] && s.none)}>
            {answers[i] || (run.queuedAnswer ? '' : skipped ? 'Skipped' : 'Not answered')}
          </span>
        </div>
      ))}
      {run.queuedAnswer && <span className={css('slate-text')}>Sent as soon as what is being made is done.</span>}
    </div>
  );
}

/** Under the newest answer, once this tab's Claude session is 80% full: compact it now, or it compacts on its own. */
function ContextNote({ chat, run }: { chat: AgentChat; run: Run }) {
  const c = run.context;
  if (!c || (!c.offer && !c.compacted)) return null;
  if (c.compacted)
    return (
      <div className={s['agent-context']} role="status">
        <span className="grow">{`Compacted. The context is now ${c.percent}% full.`}</span>
      </div>
    );
  return (
    <div className={s['agent-context']} role="status">
      <span className="grow">
        {c.error ||
          `${c.percent}% of the context is filled. Compact it now, or it will compact on its own at around 90%.`}
      </span>
      <button className="btn small" disabled={!!c.compacting} onClick={() => void compactContext(chat, run)}>
        {c.compacting ? 'Compacting…' : 'Compact now'}
      </button>
    </div>
  );
}

/** The words of a reply without the [[item:12]] marks, for copying. */
const plain = (run: Run) =>
  String(run.reply || '').replace(/\[\[(?:show:)?(item|asset):(\d+)\]\]/g, (_, t: string, n: string) => {
    const known = (run.chips || {})[`${t}:${n}`];
    return known?.link ? `${known.name} (${new URL(known.link, location.origin).href})` : known?.name || '';
  });

export function Message({ chat, run }: { chat: AgentChat; run: Run }) {
  const onPick = usePick(chat);
  const [copied, setCopied] = useState(false);
  const done = run.activity || [];
  // Thinking and working are one quiet row above the reply; what the model read and wrote, in tokens, is at its foot.
  const tally = done.filter((e) => e.type === 'activity' && e.icon === 'info');
  const steps = done.filter((e) => !tally.includes(e));
  const lastAny = [...done].reverse().find((e) => e.type === 'activity');
  const lastStep = [...steps].reverse().find((e) => e.type === 'activity');
  const onlyThought = steps.length === 1 && steps[0].type === 'thought';
  const after = run.work || [];
  return (
    <div className={s.turn}>
      <Said chat={chat} run={run} onPick={onPick} />
      {done.length > 0 && (
        <Fold
          chat={chat}
          glyphs={glyphsOf(steps.length ? steps : done)}
          title={
            onlyThought
              ? `Thought for ${span(steps[0].seconds)}`
              : `Worked ${span(run.seconds != null ? run.seconds : lastAny?.at)}`
          }
          sub={lastStep?.text ?? ''}
          state={chat.stateOf(run, 'work', () => ({}))}
          className="work"
          body={
            <>
              {onlyThought ? (
                steps[0].text && <p className={f['fold-text']}>{steps[0].text}</p>
              ) : (
                <WorkRows chat={chat} entries={steps} states={chat.stateOf(run, 'workItems', () => ({}))} />
              )}
              {tally.length > 0 && <p className={f['work-foot']}>{tally.map((e) => e.text).join(' · ')}</p>}
            </>
          }
        />
      )}
      {run.reply && <Reply chat={chat} run={run} onPick={onPick} />}
      {run === chat.runs[chat.runs.length - 1] && <ContextNote chat={chat} run={run} />}
      {questionsOf(run).length > 0 && <Asked chat={chat} run={run} />}
      {run.steps.length > 0 && <PlanView chat={chat} run={run} />}
      {after.length > 0 && (
        <Fold
          chat={chat}
          glyph="wrench"
          title={`Worked ${span((after[after.length - 1].at - (run.approvedAt || after[0].at)) / 1000)}`}
          sub={after[after.length - 1].text}
          state={chat.stateOf(run, 'after', () => ({}))}
          className="work"
          body={
            <WorkRows
              chat={chat}
              entries={after.map((w) => ({ type: 'activity', icon: w.icon, text: w.text }))}
              states={{}}
            />
          }
        />
      )}
      {run.reply && !run.error && (
        <div className={s['turn-foot']}>
          <button
            type="button"
            className={cx('icon-btn small', copied && s.done)}
            title="Copy the reply"
            aria-label="Copy the reply"
            onClick={() => {
              navigator.clipboard.writeText(plain(run)).then(
                () => setCopied(true),
                () => {},
              );
            }}
          >
            <Icon name="copy" />
          </button>
          <TurnCost chat={chat} run={run} />
        </div>
      )}
    </div>
  );
}
