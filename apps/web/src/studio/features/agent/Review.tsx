// What the checks of a plan's shots say and ask. A quiet line while they run; and, above the message box, the card for
// the questions of the newest turn and the card for what the check found (each shot with what is wrong with it, ticked
// to be made again). Number keys pick, Enter goes, Esc skips or keeps.

import { useRef, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { Icon } from '../../../common/components/Icon/Icon';
import { cx } from '../../../common/cx';
import { answer } from './actions';
import type { AgentChat } from './chat';
import { carryOn, allMade, retake, toCheck } from './checks';
import { OTHER, flagged, questionsOf, takesOf } from './shots';
import { openLarge } from './TakeParts';
import type { Run, Step } from './types';
import s from './Ask.module.css';
import r from './Results.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared.module.css';
import css1 from '../../../common/components/Shared3.module.css';
const css = classesOf(css0, css1);

/** One quiet line while the shots of a finished plan are checked. */
export function CheckLine({ chat, run, steps }: { chat: AgentChat; run: Run; steps: Step[] }) {
  if (!allMade(chat, run)) return null;
  const left = steps.filter((x) => takesOf(x).some((t) => t.reviewing || toCheck(chat, t))).length;
  if (!left) return null;
  return (
    <div className={cx(r['agent-review'], r.checking)}>
      <i className={css('cell-mark stepping')} />
      {left > 1 ? `Checking ${left} results…` : 'Checking the result…'}
    </div>
  );
}

/** What is happening to a shot's retake, in quiet words. */
export function ReviewNote({ step }: { step: Step }) {
  const all = takesOf(step);
  const newest = all[all.length - 1];
  if (newest !== step && !newest.made && !newest.error)
    return (
      <div className={cx(r['agent-review'], r.checking)}>
        <i className={css('cell-mark stepping')} />
        {`Making take ${all.length}…`}
      </div>
    );
  if (newest !== step && newest.error)
    return <div className={r['agent-review']}>{`Take ${all.length} could not be made: ${newest.error}`}</div>;
  return step.kept && step.review && !step.review.passed && all.length === 1 ? (
    <div className={r['agent-review']}>Kept as it is.</div>
  ) : null;
}

/** The card for the questions of the newest turn: one at a time, numbered options (what each does under it, the
 *  recommended one marked), and always one more, "Something else", to write an answer of one's own. */
export function AskCard({ chat, run }: { chat: AgentChat; run: Run }) {
  const list = questionsOf(run);
  const ui = chat.stateOf(run, 'ask', () => ({
    at: 0,
    picks: list.map((q) => q.default || null),
    other: list.map(() => ''),
  }));
  const q = list[ui.at];
  const last = ui.at === list.length - 1;
  const other = useRef<HTMLInputElement>(null);
  const answerOf = (i: number) => (ui.picks[i] === OTHER ? ui.other[i].trim() : ui.picks[i]);
  const ready = list.every((_, i) => answerOf(i));
  const setPick = (value: string | null) => ui.picks.map((p, i) => (i === ui.at ? value : p));
  const choose = (option: string) => {
    chat.patch(ui, { picks: setPick(option), at: option !== OTHER && !last ? ui.at + 1 : ui.at });
    if (option === OTHER) other.current?.focus();
  };
  const submit = () => {
    if (ready && !chat.busy)
      answer(
        chat,
        run,
        list.map((_, i) => answerOf(i) as string),
      );
  };
  const skip = () => {
    if (run.question) chat.patch(run.question, { skipped: true }, true);
    else chat.patch(run, { questionsSkipped: true }, true);
    chat.box?.focus();
  };
  const keys = (e: ReactKeyboardEvent) => {
    if ((e.target as Element).matches('input')) return;
    const n = Number(e.key);
    if (n >= 1 && n <= q.options.length) {
      e.preventDefault();
      choose(q.options[n - 1]);
    } else if (n === q.options.length + 1) {
      e.preventDefault();
      choose(OTHER);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      submit();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      skip();
    }
  };
  return (
    <div className={s['ask-card']} role="group" aria-label="A question from the agent" tabIndex={-1} onKeyDown={keys}>
      <div className={s['ask-head']}>
        <Icon name="chat" />
        <b>{q.text}</b>
        {list.length > 1 && <span className={s['ask-count']}>{`${ui.at + 1} of ${list.length}`}</span>}
      </div>
      <div className={s['ask-options']} role="radiogroup">
        {q.options.map((option, i) => (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={ui.picks[ui.at] === option}
            className={cx(s['ask-option'], ui.picks[ui.at] === option && s.on)}
            onClick={() => choose(option)}
            onDoubleClick={() => {
              if (last) submit();
            }}
          >
            <span className={s['ask-num']}>{`${i + 1}.`}</span>
            <span className={s['ask-words']}>
              <b>
                {option}
                {q.default === option && (
                  <i className={s['ask-rec']} title="Recommended">
                    REC
                  </i>
                )}
              </b>
              {q.details?.[i] && <span className={s['ask-detail']}>{q.details[i]}</span>}
            </span>
          </button>
        ))}
        <label className={cx(s['ask-option'], s['ask-other'], ui.picks[ui.at] === OTHER && s.on)}>
          <span className={s['ask-num']}>{`${q.options.length + 1}.`}</span>
          <input
            ref={other}
            type="text"
            placeholder="Something else"
            aria-label="Your own answer"
            value={ui.other[ui.at]}
            onChange={(e) => {
              const text = e.target.value;
              chat.patch(ui, {
                other: ui.other.map((x, i) => (i === ui.at ? text : x)),
                picks: setPick(text.trim() ? OTHER : ui.picks[ui.at] === OTHER ? null : ui.picks[ui.at]),
              });
            }}
            onFocus={() => {
              if (ui.other[ui.at].trim()) chat.patch(ui, { picks: setPick(OTHER) });
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
                e.preventDefault();
                if (ui.other[ui.at].trim() && !last) chat.patch(ui, { at: ui.at + 1 });
                else submit();
              }
              if (e.key === 'Escape') {
                e.preventDefault();
                skip();
              }
            }}
          />
        </label>
      </div>
      <div className={s['ask-foot']}>
        {list.length > 1 && (
          <button
            type="button"
            className="btn small quiet"
            disabled={ui.at === 0}
            onClick={() => chat.patch(ui, { at: ui.at - 1 })}
          >
            Back
          </button>
        )}
        {list.length > 1 && !last && (
          <button
            type="button"
            className="btn small quiet"
            disabled={!answerOf(ui.at)}
            onClick={() => chat.patch(ui, { at: ui.at + 1 })}
          >
            Next
          </button>
        )}
        <span style={{ flex: 1 }} />
        <button type="button" className="btn small quiet" onClick={skip}>
          Skip<kbd>esc</kbd>
        </button>
        {last && (
          <button type="button" className="btn small primary" disabled={!ready || chat.busy} onClick={submit}>
            {chat.generating() ? 'Send when ready' : 'Submit'}
            <kbd>↵</kbd>
          </button>
        )}
      </div>
    </div>
  );
}

/** The card for what the check of a plan found: each shot with what is wrong with it and its picture, ticked to be made
 *  again; unticked ones are kept. Words of one's own go to the agent instead. */
export function RetakeCard({ chat, run }: { chat: AgentChat; run: Run }) {
  const steps = flagged(run);
  const ui = chat.stateOf(run, 'retakes', () => ({ off: [], note: '' }));
  const chosen = steps.filter((x) => !ui.off.includes(run.steps.indexOf(x)));
  const total = chosen.reduce((n, x) => n + (x.retake?.credits ?? 0), 0);
  const typed = !!ui.note.trim();
  const toggle = (step: Step) => {
    const at = run.steps.indexOf(step);
    chat.patch(ui, { off: ui.off.includes(at) ? ui.off.filter((n) => n !== at) : [...ui.off, at] });
  };
  const decided = () => {
    void chat.save();
    chat.changed();
    carryOn(chat);
  };
  const keepAll = () => {
    steps.forEach((x) => chat.patch(x, { kept: true }));
    decided();
    chat.box?.focus();
  };
  const make = () => {
    if (chat.working || !chosen.length || total > chat.credits) return;
    steps.filter((x) => !chosen.includes(x)).forEach((x) => chat.patch(x, { kept: true }));
    chosen.forEach((x) => void retake(chat, run, x));
    decided();
  };
  const sendNote = () => {
    const words = ui.note.trim();
    if (!words) return;
    const found = steps.map((x) => `- “${x.name}”: ${x.review?.problem}`).join('\n');
    steps.forEach((x) => chat.patch(x, { kept: true }));
    chat.patch(run, {
      queuedAnswer: {
        text: `The check of your shots found:\n${found}\n\n${words}`,
        shown: words,
        ids: [],
        parts: [{ text: words }],
      },
    });
    decided();
  };
  const keys = (e: ReactKeyboardEvent) => {
    if ((e.target as Element).matches('input, [data-thumb]')) return;
    const n = Number(e.key);
    if (n >= 1 && n <= steps.length) {
      e.preventDefault();
      toggle(steps[n - 1]);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      make();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      keepAll();
    }
  };
  return (
    <div
      className={s['ask-card']}
      role="group"
      aria-label="Shots the check found a problem with"
      tabIndex={-1}
      onKeyDown={keys}
    >
      <div className={s['ask-head']}>
        <Icon name="chat" />
        <b>
          {steps.length > 1
            ? `${steps.length} shots could be closer to what was asked`
            : `“${steps[0].name}” could be closer to what was asked`}
        </b>
      </div>
      <div className={s['ask-options']}>
        {steps.map((step) => {
          const on = chosen.includes(step);
          return (
            <div key={step.name} className={cx(s['ask-option'], s['ask-shot'], on && s.on)}>
              <button
                type="button"
                className={s['ask-tick']}
                role="checkbox"
                aria-checked={on}
                title={step.retake?.why || 'Make it again with the fixed prompt'}
                onClick={() => toggle(step)}
              >
                <span className={s['ask-box']}>{on && <Icon name="check" />}</span>
                <span className={s['ask-words']}>
                  <b>{step.name}</b>
                  <span className={s['ask-detail']}>{step.review?.problem}</span>
                </span>
                <span className={s['ask-price']}>{`${step.retake?.credits} cr`}</span>
              </button>
              <button
                type="button"
                data-thumb
                className={s['ask-thumb']}
                title="Open it large"
                aria-label={`Open “${step.name}” large`}
                onClick={() => void openLarge(step.made)}
              >
                <img src={`/api/library/${step.made}/poster`} alt="" loading="lazy" />
              </button>
            </div>
          );
        })}
        <label className={cx(s['ask-option'], s['ask-other'])}>
          <input
            type="text"
            placeholder="Something else"
            aria-label="What to do instead"
            value={ui.note}
            onChange={(e) => chat.patch(ui, { note: e.target.value })}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
                e.preventDefault();
                sendNote();
              }
              if (e.key === 'Escape') {
                e.preventDefault();
                keepAll();
              }
            }}
          />
        </label>
      </div>
      <div className={s['ask-foot']}>
        <span style={{ flex: 1 }} />
        <button type="button" className="btn small quiet" onClick={keepAll}>
          {steps.length > 1 ? 'Keep all' : 'Keep it'}
          <kbd>esc</kbd>
        </button>
        <button type="button" className={cx('btn small primary', !typed && 'hidden')} onClick={sendNote}>
          Send<kbd>↵</kbd>
        </button>
        <button
          type="button"
          className={cx('btn small primary', typed && 'hidden')}
          disabled={chat.working || !chosen.length || total > chat.credits}
          title={`You have ${chat.credits} credits`}
          onClick={make}
        >
          {steps.length === 1 ? 'Retake' : chosen.length === steps.length ? 'Retake all' : `Retake ${chosen.length}`}
          {` · ${total} cr`}
          <kbd>↵</kbd>
        </button>
      </div>
    </div>
  );
}
