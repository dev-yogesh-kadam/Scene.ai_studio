// The Servers section's Claude connection card: how the studio reaches Claude Code, an Anthropic API key or the LUFI
// bridge, picked and keyed here and used from the next call to Claude, with no restart. A key is never shown or sent
// back: a blank key field keeps the one there is. Once saved it reads like the other servers' cards (the address, how it
// is, Edit and Test); Edit opens the form. See backend/scene/claude_connection.py and docs/servers.md.

import { useState } from 'react';
import { api } from '../../../common/api';
import { Field } from '../../../common/components/AuthForm';
import { Segmented } from '../../../common/components/Segmented';
import { useNotice } from '../shared/context';
import { Notice } from '../shared/ui';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared.module.css';
import css1 from '../../../common/components/Shared2.module.css';
import css2 from '../../../common/components/Shared3.module.css';
import css3 from '../../../studio/pages/create/CreatePage.module.css';
import css4 from './Servers.module.css';
import { MODE_NAMES, claudeWords, type ClaudeStatus } from './claude';
const css = classesOf(css0, css1, css2, css3, css4);

export type Connection = {
  mode: string;
  bridge_url: string;
  has_bridge_key: boolean;
  has_api_key: boolean;
  fixed: string[]; // the settings an environment variable sets (SCENE_*): shown, not changed here
  testing: string;
};
export type ConnectionData = { connection: Connection; status: ClaudeStatus; test?: ClaudeStatus };

const PATH = '/api/admin/claude-connection';
const KEPT = 'Kept unless you type a new one';

export function ClaudeConnectionCard({
  data,
  refresh,
  adding = 0,
}: {
  data: ConnectionData;
  refresh: () => Promise<void>;
  adding?: number; // counts the section's Add presses: each opens the form on the other way to reach Claude
}) {
  const [shown, setShown] = useState(data); // what the last save or test answered, until the section is asked again
  const [from, setFrom] = useState(data);
  if (from !== data) {
    setFrom(data);
    setShown(data);
  }
  const c = shown.connection;
  const [mode, setMode] = useState(c.mode);
  const [url, setUrl] = useState(c.bridge_url);
  const [bridgeKey, setBridgeKey] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [working, setWorking] = useState('');
  // Saved: the way picked has what it needs. Then the form opens only on Edit.
  const saved = c.mode === 'api_key' ? c.has_api_key : !!c.bridge_url && c.has_bridge_key;
  const [editing, setEditing] = useState(!saved);
  const [added, setAdded] = useState(adding);
  if (added !== adding) {
    setAdded(adding);
    setEditing(true);
    setMode(c.mode === 'api_key' ? 'lufi_bridge' : 'api_key');
  }
  const { notice, run } = useNotice();
  const fixed = (name: string) => c.fixed.includes(name);
  const status = shown.status;

  const act = (label: string, work: () => Promise<ConnectionData>, said: (d: ConnectionData) => string) =>
    run(async () => {
      setWorking(label);
      try {
        const got = await work();
        setShown(got);
        if (label === 'Saving…') setEditing(false);
        setBridgeKey('');
        setApiKey('');
        await refresh(); // the Overview and System sections show it too
        return said(got);
      } finally {
        setWorking('');
      }
    });
  const save = () => {
    const json: Record<string, string> = {};
    if (!fixed('claude_connection')) json.mode = mode;
    if (mode === 'lufi_bridge' && !fixed('claude_bridge_url')) json.bridge_url = url.trim();
    if (bridgeKey.trim()) json.bridge_key = bridgeKey.trim();
    if (apiKey.trim()) json.api_key = apiKey.trim();
    return act(
      'Saving…',
      () => api<ConnectionData>(PATH, { method: 'PUT', json }),
      () => 'Saved: in use from the next call.',
    );
  };
  const test = () =>
    act(
      'Testing…',
      () => api<ConnectionData>(PATH + '/test', { method: 'POST' }),
      (d) =>
        d.test?.online
          ? 'It works: ' + claudeWords(d.test) + '.'
          : 'It does not work: ' + (d.test?.detail || 'no reason given'),
    );

  return (
    <div className={css('card')}>
      <div className={css('card-head')} style={{ justifyContent: 'flex-start', gap: 10 }}>
        <span className={css('dot ' + (status.online ? 'online' : 'offline'))} />
        <h2>{MODE_NAMES[c.mode] ?? 'Claude connection'}</h2>
        {c.testing ? <span className={css('pill')}>{c.testing}</span> : null}
      </div>
      <p className="small" data-testid="claude-status">
        {status.online ? claudeWords(status) : 'Not working: ' + (status.detail || 'not checked yet')}
      </p>
      {c.testing ? (
        <p className="muted small">
          While the LUFI bridge is picked, sign-up is closed and only admins can use the agent. Picking the API key
          lifts both.
        </p>
      ) : null}
      {editing ? null : (
        <>
          <div className={css('endpoint-url')}>
            <code>{c.mode === 'api_key' ? 'Anthropic API key · kept' : c.bridge_url}</code>
            {c.mode === 'api_key' ? null : (
              <button className="btn small quiet" onClick={() => void navigator.clipboard.writeText(c.bridge_url)}>
                Copy
              </button>
            )}
          </div>
          <Notice notice={notice} />
          <div className="row">
            <button className="btn small" onClick={() => setEditing(true)}>
              Edit
            </button>
            <button className="btn small" disabled={!!working} onClick={() => void test()}>
              {working === 'Testing…' ? working : 'Test'}
            </button>
          </div>
        </>
      )}
      {editing ? (
        <>
          <div className="field">
            <div className="label">Connection</div>
            <Segmented
              choices={Object.entries(MODE_NAMES).map(([id, label]) => ({ id, label }))}
              current={mode}
              onPick={(id) => {
                if (!fixed('claude_connection')) setMode(id);
              }}
            />
          </div>
          {/* No autofill: a browser would put the console's sign-in email and password in the address and the keys. */}
          {mode === 'api_key' ? (
            <Field label="Anthropic API key">
              <input
                type="password"
                autoComplete="new-password"
                disabled={fixed('anthropic_api_key')}
                placeholder={
                  fixed('anthropic_api_key') ? 'Set by SCENE_ANTHROPIC_API_KEY' : c.has_api_key ? KEPT : 'sk-ant-…'
                }
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
              />
            </Field>
          ) : (
            <div className={css('grid2')}>
              <Field label="Bridge address">
                <input
                  type="text"
                  autoComplete="off"
                  disabled={fixed('claude_bridge_url')}
                  placeholder="http://100.64.0.7:8765"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                />
              </Field>
              <Field label="Bridge key">
                <input
                  type="password"
                  autoComplete="new-password"
                  disabled={fixed('claude_bridge_key')}
                  placeholder={
                    fixed('claude_bridge_key')
                      ? 'Set by SCENE_CLAUDE_BRIDGE_KEY'
                      : c.has_bridge_key
                        ? KEPT
                        : 'The key LUFI shows'
                  }
                  value={bridgeKey}
                  onChange={(e) => setBridgeKey(e.target.value)}
                />
              </Field>
            </div>
          )}
          <Notice notice={notice} />
          <div className="row" style={{ marginTop: 12 }}>
            <button className="btn primary" disabled={!!working} onClick={() => void save()}>
              {working === 'Saving…' ? working : 'Save'}
            </button>
            <button className="btn" disabled={!!working} onClick={() => void test()}>
              {working === 'Testing…' ? working : 'Test'}
            </button>
            {saved ? (
              <button
                className="btn quiet"
                disabled={!!working}
                onClick={() => {
                  setMode(c.mode);
                  setUrl(c.bridge_url);
                  setBridgeKey('');
                  setApiKey('');
                  setEditing(false);
                }}
              >
                Cancel
              </button>
            ) : null}
          </div>
        </>
      ) : null}
    </div>
  );
}
