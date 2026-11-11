// The studio's health in the admin console: the agent's model (Claude), maintenance mode, the watcher's alerts, and
// where alerts are sent (Telegram, ntfy). See backend/scene/health.py and phone.py.

import { useState } from 'react';
import { api } from '../../../common/api';
import { Field } from '../../../common/components/AuthForm';
import { claudeWords, type ClaudeStatus } from '../servers/claude';
import { useConsole, useNotice } from '../shared/context';
import { Facts, Notice, Table, ago, span, stamp } from '../shared/ui';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../shared/Console.module.css';
import css3 from './Shared.module.css';
import css4 from '../../../studio/pages/create/CreatePage.module.css';
const css = classesOf(css0, css1, css2, css3, css4);

const LEVEL: Record<string, string> = { critical: 'Critical', serious: 'Serious', warning: 'Warning' };

export type ModelServer = ClaudeStatus & { online: boolean; models?: string[]; url?: string; limits?: unknown };

export function ModelServerCard({ m }: { m: ModelServer }) {
  const limits = m.limits && typeof m.limits === 'object' ? Object.entries(m.limits) : [];
  return (
    <div className={css('card')}>
      <div className={css('card-head')}>
        <h2>Agent model</h2>
        <span className={css('pill ' + (m.online ? 'done' : 'failed'))}>
          {m.online ? 'Claude ready' : 'Not working'}
        </span>
      </div>
      <Facts
        pairs={[
          ['Models', (m.models || []).join(', ') || 'none'],
          ['Connection', claudeWords(m)],
          ['Claude Code runs', m.url || 'nowhere yet'],
        ]}
      />
      {!m.online && <p className="muted">{m.detail || 'Set the Claude connection in Servers & APIs.'}</p>}
      {limits.length > 0 && <h3>Usage as Claude last reported it</h3>}
      {limits.length > 0 && (
        <Table
          head={['Window', 'Used']}
          rows={limits.map(([k, v]) => [k, typeof v === 'object' ? JSON.stringify(v) : String(v)])}
        />
      )}
    </div>
  );
}

export type Maintenance = { on: boolean; text?: string; since: number; left?: number };

/** Maintenance mode: new jobs are refused and their credits given back; the waiting ones still finish. */
export function MaintenanceCard({ m }: { m: Maintenance }) {
  const { refresh } = useConsole();
  const [text, setText] = useState(m.text || '');
  const [working, setWorking] = useState('');
  const { notice, run } = useNotice();
  const set = (on: boolean, words: string) =>
    run(async () => {
      setWorking(words); // the section takes a moment to redraw: it asks both servers again
      try {
        await api('/api/admin/maintenance', { method: 'PUT', json: { on, text } });
        await refresh();
      } finally {
        setWorking('');
      }
    });
  const Button = ({ label, on, words, primary }: { label: string; on: boolean; words: string; primary?: boolean }) => (
    <button className={primary ? 'btn primary' : 'btn'} disabled={!!working} onClick={() => void set(on, words)}>
      {working === words ? words : label}
    </button>
  );
  return (
    <div className={css('card')}>
      <div className={css('card-head')}>
        <h2>Maintenance</h2>
        <span className={css('pill ' + (m.on ? 'running' : 'done'))}>{m.on ? 'On' : 'Off'}</span>
      </div>
      <p className="muted small">
        For a restart, an update or work on the render PC. While it is on, nobody can start a new job: they are told
        your message, which also shows at the top of the studio, and get their credits back. Jobs already waiting or
        running still finish.
      </p>
      {m.on && (
        <Facts
          pairs={[
            ['On since', stamp(m.since)],
            [
              'Left to finish',
              m.left ? `${m.left} job${m.left === 1 ? '' : 's'}` : 'None: the queue is empty, it is safe to restart',
            ],
          ]}
        />
      )}
      <Field label="Message to users">
        <textarea
          rows={2}
          maxLength={300}
          placeholder="The studio is under maintenance. New jobs can start again soon."
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </Field>
      <Notice notice={notice} />
      <div className="row" style={{ marginTop: 12 }}>
        {m.on ? (
          <>
            {Button({ label: 'Update message', on: true, words: 'Saving…' })}
            {Button({ label: 'Turn off', on: false, words: 'Turning off…', primary: true })}
          </>
        ) : (
          Button({ label: 'Turn on', on: true, words: 'Turning on…', primary: true })
        )}
      </div>
    </div>
  );
}

type Alert = { level: string; text: string; tab?: string; started: number; ended?: number };
export type Alerts = { open: Alert[]; recent: Alert[]; every: number; confirm: number; phone: Phone };

/** What the watcher found: open alerts first, then the latest ones and how long each lasted. */
export function AlertsCard({ a }: { a: Alerts }) {
  const { go } = useConsole();
  const past = a.recent.filter((x) => x.ended);
  return (
    <div className={css('card')}>
      <div className={css('card-head')}>
        <h2>Alerts</h2>
        <span className={css('pill ' + (a.open.length ? 'failed' : 'done'))}>
          {a.open.length ? `${a.open.length} open` : 'All well'}
        </span>
      </div>
      <p className="muted small">{`The studio checks its servers, disk, backups and queue every ${a.every} seconds, also while nobody has the console open. A problem found ${a.confirm} times in a row is an alert: it is sent to your phone ${a.phone.on ? '(set up in Settings)' : '(once Phone alerts are set up in Settings)'}, and so is its end.`}</p>
      {a.open.length ? (
        <div className={css('attention')}>
          {a.open.map((x, i) => (
            <button key={i} className={css('alert ' + x.level)} onClick={() => go(x.tab || 'system')}>
              <span className={css('alert-level')}>{LEVEL[x.level] || x.level}</span>
              <span className={css('alert-text')}>{x.text}</span>
              <span className="muted small">{'since ' + stamp(x.started)}</span>
            </button>
          ))}
        </div>
      ) : (
        <p className="muted">Nothing is wrong right now.</p>
      )}
      {past.length > 0 && <h3>Earlier</h3>}
      {past.length > 0 && (
        <Table
          head={['', 'What', 'When', 'Lasted']}
          rows={past.slice(0, 15).map((x) => [
            <span
              key="l"
              className={css('alert ' + x.level + ' static')}
              style={{ padding: 0, border: 0, margin: 0, background: 'none' }}
            >
              <span className={css('alert-level')}>{LEVEL[x.level] || x.level}</span>
            </span>,
            <span key="t" className="small">
              {x.text}
            </span>,
            ago(x.started),
            span((x.ended as number) - x.started),
          ])}
        />
      )}
    </div>
  );
}

export type Phone = { on: boolean; telegram_token_end?: string; telegram_chat: string; ntfy_url: string };

/** Where alerts go: a Telegram bot of the admin's own, or an ntfy topic, or both. */
export function PhoneCard({ phone }: { phone: Phone }) {
  const { refresh } = useConsole();
  const [token, setToken] = useState('');
  const [chat, setChat] = useState(phone.telegram_chat);
  const [ntfy, setNtfy] = useState(phone.ntfy_url);
  const [topic] = useState(() => `https://ntfy.sh/scene-${Math.random().toString(36).slice(2, 10)}`);
  const { notice, setNotice, run } = useNotice();
  const put = (json: unknown) => api('/api/admin/alerts/phone', { method: 'PUT', json });
  const test = () =>
    run(async () => {
      const { results } = await api<{ results: Record<string, string> }>('/api/admin/alerts/test', { method: 'POST' });
      const failedOnes = Object.entries(results).filter(([, problem]) => problem);
      setNotice({
        ok: !failedOnes.length,
        text: failedOnes.length
          ? failedOnes.map(([channel, problem]) => `${channel === 'ntfy' ? 'ntfy' : 'Telegram'}: ${problem}.`).join(' ')
          : `Sent to ${Object.keys(results)
              .map((c) => (c === 'ntfy' ? 'ntfy' : 'Telegram'))
              .join(' and ')}. Check your phone.`,
      });
    });
  return (
    <div className={css('card narrow')}>
      <div className={css('card-head')}>
        <h2>Phone alerts</h2>
        <span className={css('pill ' + (phone.on ? 'done' : 'failed'))}>{phone.on ? 'On' : 'Off'}</span>
      </div>
      <p className="muted small">
        When the render server or the model server stops answering, the disk fills, backups stop, jobs fail one after
        another or wait too long, your phone hears of it, and again when it is over. Use either or both.
      </p>
      <h3>Telegram</h3>
      <ol className={css('steps')}>
        <li>In Telegram, talk to @BotFather, send /newbot and follow it. It gives you a token.</li>
        <li>Paste the token here, then open your new bot and press Start.</li>
        <li>Press Find my chat.</li>
      </ol>
      <Field label="Bot token">
        <input
          type="password"
          autoComplete="off"
          placeholder={phone.telegram_token_end ? `Saved (ends in ${phone.telegram_token_end})` : '123456789:AAH…'}
          value={token}
          onChange={(e) => setToken(e.target.value)}
        />
      </Field>
      <Field label="Chat">
        <div className="row">
          <input
            type="text"
            value={chat}
            placeholder="Found for you, or a number"
            onChange={(e) => setChat(e.target.value)}
          />
          <button
            className="btn small"
            onClick={() =>
              void run(async () => {
                if (token) await put({ telegram_token: token });
                const found = await api<{ telegram_chat: string }>('/api/admin/alerts/telegram-chat', {
                  method: 'POST',
                });
                setChat(found.telegram_chat);
                return `Found your chat (${found.telegram_chat}) and saved it.`;
              })
            }
          >
            Find my chat
          </button>
        </div>
      </Field>
      <h3>ntfy</h3>
      <p className="muted small">
        Install the ntfy app, subscribe to a topic of your own (a name nobody can guess, like the one suggested), and
        paste its address here.
      </p>
      <Field label="Topic address">
        <input type="text" value={ntfy} placeholder={topic} onChange={(e) => setNtfy(e.target.value)} />
      </Field>
      <Notice notice={notice} />
      <div className="row" style={{ marginTop: 12 }}>
        <button
          className="btn primary"
          onClick={() =>
            void run(async () => {
              await put({ telegram_token: token, telegram_chat: chat, ntfy_url: ntfy });
              await refresh();
            })
          }
        >
          Save
        </button>
        <button className="btn" disabled={!phone.on} onClick={() => void test()}>
          Send a test
        </button>
        {phone.telegram_token_end && (
          <button
            className="btn quiet danger"
            onClick={() =>
              void run(async () => {
                await put({ telegram: false });
                await refresh();
              })
            }
          >
            Remove Telegram
          </button>
        )}
      </div>
    </div>
  );
}
