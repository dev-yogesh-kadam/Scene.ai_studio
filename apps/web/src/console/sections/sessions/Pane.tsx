// One session watched as it happens: who it is, how full its context is, and its events, new ones coming in by themselves.

import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { api } from '../../../common/api';
import { ago, number, stamp } from '../shared/ui';
import { Fullness, StatePill, tokens, where, type SessionRow } from './parts';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../../../common/components/Shared4.module.css';
import css3 from './Pane.module.css';
const css = classesOf(css0, css1, css2, css3);

const KIND: Record<string, string> = {
  user: 'User',
  prompt: 'Sent',
  thinking: 'Thinking',
  text: 'Claude',
  tool_call: 'Tool',
  tool_result: 'Result',
  answer: 'Answer',
  compact: 'Compact',
  model: 'Model',
  error: 'Error',
  note: 'Note',
};
const FOLDED = new Set(['prompt', 'thinking', 'tool_result']); // long: shown folded, opened with a click
const POLL = 2000;

type Event = {
  id: number;
  kind: string;
  text: string;
  at: number;
  data?: { input?: unknown; steps?: number; pre_tokens?: number; post_tokens?: number };
};
type Session = SessionRow & { title?: string; agent: string; claude_id?: string; started: number; resume?: string };
type Got = { session: Session; events: Event[]; more?: boolean };

function Line({ e }: { e: Event }) {
  let text = e.text;
  if (e.kind === 'tool_call' && e.data?.input) text = `${e.text}(${JSON.stringify(e.data.input)})`;
  if (e.kind === 'answer' && e.data)
    text += e.data.steps ? `\n(${e.data.steps} step${e.data.steps === 1 ? '' : 's'} planned)` : '';
  if (e.kind === 'compact' && e.data?.pre_tokens)
    text += ` · ${tokens(e.data.pre_tokens)} → ${tokens(e.data.post_tokens || 0)} tokens`;
  const long = FOLDED.has(e.kind) || e.text.length > 600;
  return (
    <div className={css('ses-line k-' + e.kind)}>
      <span className={css('ses-time')} title={stamp(e.at)}>
        {new Date(e.at * 1000).toLocaleTimeString([], {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hourCycle: 'h23',
        })}
      </span>
      <span className={css('ses-kind')}>{KIND[e.kind] || e.kind}</span>
      {long ? (
        <details>
          <summary>
            {text.split('\n')[0].slice(0, 160) || '(empty)'}
            <span className="muted">{` · ${number(text.length)} characters`}</span>
          </summary>
          <pre>{text}</pre>
        </details>
      ) : (
        <pre>{text}</pre>
      )}
    </div>
  );
}

function Resume({ command }: { command: string }) {
  const [word, setWord] = useState('Copy');
  return (
    <div className={css('ses-resume')}>
      <code>{command}</code>
      <button
        className="btn small"
        onClick={() => {
          navigator.clipboard.writeText(command).then(
            () => {
              setWord('Copied');
              setTimeout(() => setWord('Copy'), 1500);
            },
            () => setWord('Select it and copy'),
          );
        }}
      >
        {word}
      </button>
    </div>
  );
}

export function Pane({ sessionRef, alone }: { sessionRef: string; alone: boolean }) {
  const [session, setSession] = useState<Session | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [started, setStarted] = useState(false);
  const [error, setError] = useState('');
  const log = useRef<HTMLDivElement>(null);
  const stick = useRef(false);
  useEffect(() => {
    let live = true;
    let after = 0;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const got = await api<Got>(`/api/admin/sessions/${sessionRef}?after=${after}`);
        if (!live) return;
        setSession(got.session);
        const n = log.current;
        stick.current = !!n && (n.scrollHeight - n.scrollTop - n.clientHeight < 40 || got.events.length === 500);
        if (got.events.length) {
          setEvents((was) => [...was, ...got.events]);
          after = got.events[got.events.length - 1].id;
        }
        setStarted(true);
        setError('');
        if (got.more) {
          timer = setTimeout(() => void poll(), 50); // a long story comes in pages
          return;
        }
      } catch (e) {
        if (!live) return;
        setError((e as Error).message);
        if ((e as { status?: number }).status === 404) return;
      }
      timer = setTimeout(() => void poll(), document.hidden ? POLL * 5 : POLL);
    };
    void poll();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [sessionRef]);
  useLayoutEffect(() => {
    if (stick.current && log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [events]);
  const s = session;
  return (
    <div className={css('card ses-pane' + (alone ? ' alone' : ''))}>
      <div className={css('ses-head')}>
        {s ? (
          <>
            <div className="grow">
              <b>{s.title || 'Studio session'}</b>
              <div className="muted small">{s.ref}</div>
            </div>
            <StatePill state={s.state} />
          </>
        ) : (
          <b>{sessionRef}</b>
        )}
      </div>
      <div className={css('ses-facts')}>
        {s && (
          <>
            <dl className={css('facts')}>
              <dt>Person</dt>
              <dd>{`${s.user_name} · ${s.user_email}`}</dd>
              <dt>Project</dt>
              <dd>
                {where(s) + (s.project_ref ? ` (${[s.parent_ref, s.project_ref].filter(Boolean).join(' › ')})` : '')}
              </dd>
              <dt>Agent tab</dt>
              <dd>{s.agent}</dd>
              <dt>Claude session</dt>
              <dd>{s.claude_id || 'not started yet'}</dd>
              <dt>Model</dt>
              <dd>{s.model || '—'}</dd>
              <dt>Context</dt>
              <dd>
                <Fullness s={s} />
                <span className="muted small">{`${tokens(s.context_tokens)} of ${tokens(s.context_window)}`}</span>
              </dd>
              <dt>Messages</dt>
              <dd>{number(s.messages)}</dd>
              <dt>Started</dt>
              <dd>{stamp(s.started)}</dd>
              <dt>Last active</dt>
              <dd>{ago(s.active)}</dd>
            </dl>
            {s.resume && <Resume command={s.resume} />}
          </>
        )}
      </div>
      <div ref={log} className={css('ses-log')} role="log" aria-live="polite">
        {error ? (
          <p className="error">{error}</p>
        ) : started && !events.length ? (
          <p className="muted">Nothing has happened in this session yet.</p>
        ) : (
          events.map((e) => <Line key={e.id} e={e} />)
        )}
      </div>
    </div>
  );
}
