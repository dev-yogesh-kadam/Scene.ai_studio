// One run of the agent in the console: its calls in order, the words of each, a replay with another model, and keeping a
// call in a Langfuse dataset.

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../../../common/api';
import { Drawer } from '../shared/Drawer';
import { Facts, Section, number, span, stamp } from '../shared/ui';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from './RunDrawer.module.css';
import css2 from '../shared/Console.module.css';
const css = classesOf(css0, css1, css2);

export type Langfuse = { url: string; project: string };
export type RunRow = {
  run: string;
  started: number;
  seconds: number;
  tokens: number;
  user_name?: string;
  user_email?: string;
  purposes: string[];
  models: string[];
  tools: string[];
  calls: number;
  errors: number;
  trace?: string;
};
type Call = {
  id: number;
  purpose?: string;
  tool?: string;
  model?: string;
  asked?: string;
  seconds: number;
  prompt_tokens: number;
  answer_tokens: number;
  error?: string;
};
type Found = { user?: { name: string; email: string }; calls: Call[]; langfuse?: Langfuse; trace?: string };
type Words = { messages: { role: string; images?: number; content?: unknown }[]; answer: unknown };

export const tokens = (n: number) =>
  n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e4 ? Math.round(n / 1e3) + 'k' : number(n);

/** Where a run's trace opens in Langfuse, when one is set in Servers & APIs (docs/langfuse.md). */
export function TraceLink({
  langfuse,
  trace,
  label = 'Open in Langfuse',
}: {
  langfuse?: Langfuse | null;
  trace?: string;
  label?: string;
}) {
  if (!langfuse || !trace) return null;
  return (
    <a
      href={`${langfuse.url}/project/${encodeURIComponent(langfuse.project)}/traces/${trace}`}
      target="_blank"
      rel="noopener noreferrer"
      className="small"
      onClick={(e) => e.stopPropagation()}
    >
      {label}
    </a>
  );
}

/** Keep a call in a Langfuse dataset: what was sent as its input, its answer as what is expected. */
function DatasetRow({ call }: { call: Call }) {
  const [name, setName] = useState('agent-' + (call.purpose || 'calls').replace(/\s+/g, '-'));
  const [note, setNote] = useState('');
  const [said, setSaid] = useState({ text: '', bad: false });
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      const r = await api<{ dataset: string }>(`/api/admin/agent/calls/${call.id}/dataset`, {
        method: 'POST',
        json: { dataset: name, note },
      });
      setSaid({ text: `Kept in “${r.dataset}”.`, bad: false });
    } catch (e) {
      setSaid({ text: (e as Error).message, bad: true });
    }
    setBusy(false);
  };
  return (
    <div className="row" style={{ marginTop: 8 }}>
      <input type="text" placeholder="Dataset name" value={name} onChange={(e) => setName(e.target.value)} />
      <input type="text" placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
      <button className="btn small" disabled={busy} onClick={() => void save()}>
        Save to dataset
      </button>
      <span className={said.bad ? 'error small' : 'muted small'}>{said.text}</span>
    </div>
  );
}

type Replayed = {
  model: string;
  seconds: number;
  usage: { prompt: number; answer: number };
  pictures_left_out?: number;
  answer: unknown;
};

function CallWords({ call, models }: { call: Call; models: string[] }) {
  const query = useQuery({
    queryKey: ['console', 'call', call.id],
    queryFn: () => api<{ exchange: Words | null }>(`/api/admin/agent/calls/${call.id}`),
  });
  const [model, setModel] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ done?: Replayed; error?: string }>({});
  if (!query.data) return null;
  const words = query.data.exchange;
  const replay = async () => {
    setBusy(true);
    try {
      setResult({
        done: await api<Replayed>(`/api/admin/agent/calls/${call.id}/replay`, { method: 'POST', json: { model } }),
      });
    } catch (e) {
      setResult({ error: (e as Error).message });
    }
    setBusy(false);
  };
  const r = result.done;
  return (
    <>
      {words ? (
        <div>
          {words.messages.map((m, i) => (
            <details key={i} className={css('words-part')}>
              <summary>{`${m.role}${m.images ? ` · ${m.images} picture${m.images === 1 ? '' : 's'}` : ''} · ${number(String(m.content || '').length)} characters`}</summary>
              <pre className={css('words')}>{String(m.content || '')}</pre>
            </details>
          ))}
          <details className={css('words-part')} open>
            <summary>answer</summary>
            <pre className={css('words')}>{JSON.stringify(words.answer, null, 2)}</pre>
          </details>
        </div>
      ) : (
        <p className="muted small">Its words are no longer kept: they are kept for a week.</p>
      )}
      {words && (
        <div className="row" style={{ marginTop: 8 }}>
          <datalist id="agent-models-drawer">
            {models.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
          <input
            type="text"
            list="agent-models-drawer"
            placeholder={call.model || 'the main model'}
            value={model}
            onChange={(e) => setModel(e.target.value)}
          />
          <button className="btn small" disabled={busy} onClick={() => void replay()}>
            {busy ? 'Asking…' : 'Replay'}
          </button>
        </div>
      )}
      {words && <DatasetRow call={call} />}
      <div>
        {result.error && <p className="error">{result.error}</p>}
        {r && (
          <>
            <p className="muted small">
              {`${r.model} · ${span(r.seconds)} · read ${tokens(r.usage.prompt)}, wrote ${tokens(r.usage.answer)}` +
                (r.pictures_left_out
                  ? ` · its ${r.pictures_left_out} picture${r.pictures_left_out === 1 ? ' was' : 's were'} not kept, so not sent`
                  : '')}
            </p>
            <pre className={css('words')}>{JSON.stringify(r.answer, null, 2)}</pre>
          </>
        )}
      </div>
    </>
  );
}

function CallRow({ call, n, models }: { call: Call; n: number; models: string[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={css('version')}>
      <div className="row">
        <b>{`${n}. ${call.purpose}`}</b>
        {call.tool && <span className={css('pill running')}>{call.tool}</span>}
        <span className="muted small">{`${call.model || call.asked || '?'} · ${span(call.seconds)} · read ${tokens(call.prompt_tokens)}, wrote ${tokens(call.answer_tokens)}`}</span>
        {!open && (
          <button className="btn small quiet" onClick={() => setOpen(true)}>
            Words and replay
          </button>
        )}
      </div>
      {call.error && <p className="error small">{call.error}</p>}
      {open && <CallWords call={call} models={models} />}
    </div>
  );
}

export function RunDrawer({ run, models, onClose }: { run: RunRow; models: string[]; onClose: () => void }) {
  const query = useQuery({
    queryKey: ['console', 'run', run.run],
    queryFn: () => api<Found>('/api/admin/agent/runs/' + encodeURIComponent(run.run)),
  });
  const found = query.data;
  return (
    <Drawer title="Agent run" onClose={onClose}>
      {() =>
        !found ? (
          <p className={query.error ? 'error' : 'muted'}>{query.error ? query.error.message : 'Loading…'}</p>
        ) : (
          <>
            <Section title="Run">
              <Facts
                pairs={[
                  [
                    'Who',
                    found.user ? `${found.user.name} (${found.user.email})` : 'The studio itself (a job, a check)',
                  ],
                  ['Started', stamp(run.started)],
                  ['Calls', number(found.calls.length)],
                  ['Time', span(run.seconds)],
                  ['Tokens', tokens(run.tokens)],
                  ...(found.langfuse && found.trace
                    ? ([['Langfuse', <TraceLink key="l" langfuse={found.langfuse} trace={found.trace} />]] as const)
                    : []),
                ]}
              />
            </Section>
            <Section title="Calls, in order">
              {found.calls.map((c, i) => (
                <CallRow key={c.id} call={c} n={i + 1} models={models} />
              ))}
            </Section>
          </>
        )
      }
    </Drawer>
  );
}
