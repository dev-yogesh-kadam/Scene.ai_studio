// A row that folds open ("Thought for 6s", "Worked 12s · Checked the result"), and the rows of the agent's work.
// `state` keeps whether it is open, on the turn, so it stays open when the conversation is drawn again.

import type { ReactNode } from 'react';
import { Icon, type IconName } from '../../../common/components/Icon/Icon';
import { cx } from '../../../common/cx';
import type { AgentChat } from './chat';
import { span } from './shots';
import type { Activity, FoldState } from './types';
import s from './Fold.module.css';

export function Fold({
  chat,
  glyph,
  glyphs,
  title,
  sub = '',
  state,
  body = null,
  className,
  stretch = false,
}: {
  chat: AgentChat;
  glyph?: IconName;
  glyphs?: IconName[];
  title: string;
  sub?: string;
  state: FoldState;
  body?: ReactNode;
  className?: 'work' | 'info' | 'cancelled' | 'nested';
  stretch?: boolean; // as wide as what holds it
}) {
  const has = Boolean(body);
  const inside = (
    <>
      {glyphs?.length ? (
        <span className={s['fold-glyphs']} aria-hidden="true">
          {glyphs.map((g) => (
            <span key={g}>
              <Icon name={g} />
            </span>
          ))}
        </span>
      ) : glyph ? (
        <Icon name={glyph} />
      ) : null}
      <span className={s['fold-title']}>{title}</span>
      {sub && <span className={s['fold-sub']}>{sub}</span>}
      {has && (
        <span className={s['fold-caret']} aria-hidden="true">
          <Icon name={state.open ? 'down' : 'right'} />
        </span>
      )}
    </>
  );
  return (
    <div className={cx(s.fold, className && s[className], state.open && s.open, stretch && s.stretch)}>
      {has ? (
        <button
          type="button"
          className={s['fold-head']}
          aria-expanded={Boolean(state.open)}
          onClick={() => chat.patch(state, { open: !state.open })}
        >
          {inside}
        </button>
      ) : (
        <div className={s['fold-head']}>{inside}</div>
      )}
      {has && state.open && <div className={s['fold-body']}>{body}</div>}
    </div>
  );
}

const WORK_ICONS: Record<string, IconName> = {
  attach: 'attachment',
  bulb: 'bulb',
  book: 'book',
  look: 'eye',
  skill: 'skill',
  retry: 'retry',
  skip: 'skip',
  plan: 'check',
  queue: 'queue',
  wait: 'clock',
  ready: 'film',
  check: 'check',
  warn: 'skip',
  status: 'wrench',
};

/** The marks of some work, one of each kind it did and at most three: what a closed fold shows before its title. */
export function glyphsOf(entries: Activity[]) {
  const names: IconName[] = [];
  for (const entry of entries) {
    const name = entry.type === 'thought' ? 'bulb' : WORK_ICONS[entry.icon ?? ''] || 'wrench';
    if (!names.includes(name)) names.push(name);
  }
  return names.slice(0, 3);
}

/** The rows of the agent's work. A thought among them is a fold of its own. `newFrom`: rows from here on fade in. */
export function WorkRows({
  chat,
  entries,
  states,
  newFrom = Infinity,
}: {
  chat: AgentChat;
  entries: Activity[];
  states: Record<number, FoldState>;
  newFrom?: number;
}) {
  return entries.map((entry, i) =>
    entry.type === 'thought' ? (
      <Fold
        key={i}
        chat={chat}
        glyph="bulb"
        title={`Thought for ${span(entry.seconds)}`}
        state={(states[i] ??= {})}
        body={entry.text ? <p className={s['fold-text']}>{entry.text}</p> : null}
        className="nested"
      />
    ) : (
      <div key={i} className={cx(s['work-row'], i >= newFrom && s['row-in'])}>
        <Icon name={WORK_ICONS[entry.icon ?? ''] || 'wrench'} />
        <span>{entry.text}</span>
      </div>
    ),
  );
}
