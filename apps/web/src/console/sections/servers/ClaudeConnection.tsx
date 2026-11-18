// Servers & APIs → Providers: the card of Claude on this PC (ClaudeOnThisPC), and what /api/admin/claude-connection
// answers (backend/scene/api/admin.py, claude_connection.py): the connection picked (never a key, only whether there
// is one) and how it is now. Which provider the agent uses is picked in Providers.tsx ("The agent uses"); an Anthropic
// API key is added there like any provider's key. See docs/servers.md, "Claude on this PC".

import { useState } from 'react';
import { api } from '../../../common/api';
import { useNotice } from '../shared/context';
import { Notice } from '../shared/ui';
import { Field } from '../../../common/components/AuthForm';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared.module.css';
import css1 from '../../../common/components/Shared2.module.css';
import css2 from '../../../common/components/Shared3.module.css';
import css3 from '../../../studio/pages/create/CreatePage.module.css';
import css4 from './Servers.module.css';
import { runningWords, signInWords, usageWords, type ClaudeStatus } from './claude';
const css = classesOf(css0, css1, css2, css3, css4);

export type Connection = {
  mode: string; // "this_pc" or "api_key"
  has_api_key: boolean;
  fixed: string[]; // the settings an environment variable sets (SCENE_*): shown, not changed here
  testing: string;
};
export type ConnectionData = { connection: Connection; status: ClaudeStatus; test?: ClaudeStatus };

const PATH = '/api/admin/claude-connection';

/** Servers & APIs → Providers' card of Claude on this PC: no key and no address. How Claude Code here is signed in,
 * how much of the plan's 5-hour window and week is used (as the last call reported it), the calls running, and Check,
 * which asks Claude Code's sign-in again now (no call to Claude, nothing spent). Sign in (Switch account when signed
 * in) opens the claude.com sign-in page and takes the code it shows; Sign out signs Claude Code here out. */
export function ClaudeOnThisPC({
  name,
  inUse,
  status,
  testing,
  refresh,
}: {
  name: string;
  inUse: boolean; // the agent uses it: status is its own
  status?: ClaudeStatus; // the connection in use, from /api/admin/claude-connection
  testing: string;
  refresh: () => Promise<void>;
}) {
  const [checked, setChecked] = useState<ClaudeStatus | null>(null);
  const [from, setFrom] = useState(status);
  if (from !== status) {
    setFrom(status);
    setChecked(null);
  }
  const [working, setWorking] = useState(false);
  const [link, setLink] = useState(''); // the claude.com page of a sign-in waiting for its code
  const [code, setCode] = useState('');
  const [signing, setSigning] = useState('');
  const { notice, run } = useNotice();
  const s = checked ?? status ?? {};
  const busy = working || !!signing;
  const signIn = () =>
    run(async () => {
      setSigning('Starting…');
      try {
        const got = await api<{ link: string }>(PATH + '/signin', { method: 'POST' });
        setLink(got.link);
        setCode('');
        window.open(got.link, '_blank', 'noopener');
        return 'Sign in on the claude.com page that opened, then paste its code here.';
      } finally {
        setSigning('');
      }
    });
  const sendCode = () =>
    run(async () => {
      setSigning('Signing in…');
      try {
        const got = await api<ConnectionData>(PATH + '/signin/code', { method: 'POST', json: { code: code.trim() } });
        setLink('');
        setCode('');
        setChecked(got.status);
        await refresh();
        return 'Signed in' + (got.status.account ? ' as ' + got.status.account : '') + '.';
      } finally {
        setSigning('');
      }
    });
  const cancel = () => {
    setLink('');
    setCode('');
    void api(PATH + '/signin', { method: 'DELETE' }).catch(() => undefined);
  };
  const signOut = () =>
    run(async () => {
      if (!window.confirm('Sign Claude Code on this PC out? The agent stops until someone signs in again.')) return;
      setSigning('Signing out…');
      try {
        const got = await api<ConnectionData>(PATH + '/signout', { method: 'POST' });
        setChecked(got.status);
        await refresh();
        return 'Signed out.';
      } finally {
        setSigning('');
      }
    });
  const check = () =>
    run(async () => {
      setWorking(true);
      try {
        const got = await api<ConnectionData>(PATH + '/test', { method: 'POST' });
        setChecked(got.test ?? got.status);
        await refresh();
        return got.test?.online ? 'Checked: it works.' : 'Checked: ' + (got.test?.detail || 'it does not work.');
      } finally {
        setWorking(false);
      }
    });
  return (
    <div className={css('card')} data-testid="claude-on-this-pc">
      <div className={css('card-head')} style={{ justifyContent: 'flex-start', gap: 10 }}>
        <span className={css('dot ' + (inUse ? (s.online ? 'online' : 'offline') : ''))} />
        <h2>{name}</h2>
        {inUse ? <span className={css('pill')}>The agent uses it</span> : null}
        {inUse && testing ? <span className={css('pill')}>{testing}</span> : null}
      </div>
      {inUse ? (
        <>
          <p className={'small' + (s.online ? '' : ' error')} data-testid="claude-signin">
            {signInWords(s)}
          </p>
          <p className="muted small" data-testid="claude-usage">
            {usageWords(s)}
          </p>
          <p className="muted small">{runningWords(s)}</p>
          <Notice notice={notice} />
          {link ? (
            <div data-testid="claude-signin-code">
              <p className="muted small">
                1. Sign in on{' '}
                <a href={link} target="_blank" rel="noopener noreferrer">
                  the claude.com sign-in page
                </a>{' '}
                with the Claude account the agent should use. 2. Paste the code it shows here.
              </p>
              <Field label="Code">
                <input
                  type="text"
                  autoComplete="off"
                  spellCheck={false}
                  aria-label="Code"
                  maxLength={512}
                  placeholder="Paste the code from claude.com"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && code.trim()) void sendCode();
                  }}
                />
              </Field>
              <div className="row">
                <button className="btn small" disabled={busy || !code.trim()} onClick={() => void sendCode()}>
                  {signing || 'Sign in'}
                </button>
                <button className="btn small ghost" disabled={busy} onClick={cancel}>
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="row">
              <button className="btn small" disabled={busy} onClick={() => void check()}>
                {working ? 'Checking…' : 'Check'}
              </button>
              <button className="btn small" disabled={busy} onClick={() => void signIn()}>
                {signing || (s.signed_in ? 'Switch account' : 'Sign in')}
              </button>
              {s.signed_in ? (
                <button className="btn small ghost" disabled={busy} onClick={() => void signOut()}>
                  Sign out
                </button>
              ) : null}
            </div>
          )}
          <p className="muted small">
            This is the Claude Code sign-in on this PC, so it is also the account Claude Code in a terminal here uses.
          </p>
        </>
      ) : (
        <p className="muted small">
          Not in use. Pick it under The agent uses, and the agent runs on the account Claude Code is signed in with on
          this PC.
        </p>
      )}
    </div>
  );
}
