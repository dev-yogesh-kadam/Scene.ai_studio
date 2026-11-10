// The console's Servers section: the ComfyUI servers the renders run on, and Langfuse, which is sent every call of the
// agent's models. Each can be added, switched off or removed while the studio runs; a waiting render goes to the first
// one that is free. See backend/scene/endpoints.py and langfuse_trace.py.

import { useRef, useState } from 'react';
import { api } from '../../../common/api';
import { Field } from '../../../common/components/AuthForm';
import { useConsole, useSection } from '../shared/context';
import { Loaded, failed, sure } from '../shared/ui';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared.module.css';
import css1 from '../../../common/components/Shared2.module.css';
import css2 from '../../../common/components/Shared3.module.css';
import css3 from './Servers.module.css';
import css4 from '../../../studio/pages/create/CreatePage.module.css';
const css = classesOf(css0, css1, css2, css3, css4);

const ABOUT: Record<string, string> = {
  comfy:
    'Renders go to the first one that answers and is not rendering. The first is the main one: uploaded files are kept there and copied to the others when a render needs them.',
  langfuse:
    "Every call of the agent's models is sent here too: the words, the answer, the tokens and what they cost, one trace per turn and one session per Agent tab. The keys are the project's, from Langfuse's Settings → API keys.",
};
const PLACEHOLDER: Record<string, string> = { comfy: 'http://100.123.221.34:8188', langfuse: 'http://127.0.0.1:3000' };

type Endpoint = {
  id: number;
  kind: string;
  name: string;
  url: string;
  active: number | boolean;
  online?: boolean;
  running?: boolean;
  detail?: string;
  has_key?: boolean;
};
type Row = Partial<Endpoint> & { kind: string };
type Data = { kinds: Record<string, string>; endpoints: Endpoint[] };

/** The form for one: a new one (`row` without an id) or an existing one. */
function Form({ kinds, row, close }: { kinds: Record<string, string>; row: Row; close: () => void }) {
  const { refresh } = useConsole();
  const [kind, setKind] = useState(row.kind);
  const [name, setName] = useState(row.name || '');
  const [url, setUrl] = useState(row.url || '');
  const [active, setActive] = useState(row.active !== 0);
  const [pub, setPub] = useState('');
  const [secret, setSecret] = useState('');
  const [notice, setNotice] = useState('');
  const [saving, setSaving] = useState(false);
  const busy = useRef(false); // one click, one server: a second click while it saves does nothing
  const kept = row.has_key ? 'Kept unless you type new ones' : '';
  const save = async () => {
    if (busy.current) return;
    const body: Record<string, unknown> = { kind, name, url, active };
    if (kind === 'langfuse' && (pub.trim() || secret.trim())) {
      if (!pub.trim() || !secret.trim()) return setNotice('Type both keys, or neither to keep the ones it has.');
      body.api_key = pub.trim() + ':' + secret.trim();
    }
    busy.current = true;
    setSaving(true);
    try {
      await api('/api/admin/endpoints' + (row.id ? '/' + row.id : ''), { method: row.id ? 'PUT' : 'POST', json: body });
      close();
      await refresh();
    } catch (e) {
      setNotice((e as Error).message);
      setSaving(false);
    }
    busy.current = false;
  };
  return (
    <div className={css('card')}>
      {/* No autofill: a browser would put the console's sign-in email and password in the address and the key. */}
      <div className={css('grid2')}>
        <Field label="What it is">
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            {Object.entries(kinds).map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Name">
          <input
            type="text"
            autoComplete="off"
            autoFocus
            maxLength={60}
            value={name}
            placeholder="Zoro, Kaggle…"
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <Field label="Address">
          <input
            type="text"
            autoComplete="off"
            value={url}
            placeholder={PLACEHOLDER[kind]}
            onChange={(e) => setUrl(e.target.value)}
          />
        </Field>
      </div>
      {kind === 'langfuse' && (
        <div className={css('grid2')}>
          <Field label="Public key">
            <input
              type="text"
              autoComplete="off"
              placeholder={kept || 'pk-lf-…'}
              value={pub}
              onChange={(e) => setPub(e.target.value)}
            />
          </Field>
          <Field label="Secret key">
            <input
              type="password"
              autoComplete="new-password"
              placeholder={kept || 'sk-lf-…'}
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
            />
          </Field>
        </div>
      )}
      <label className="check">
        <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
        In use
      </label>
      <p className={'notice' + (notice ? ' error' : '')}>{notice}</p>
      <div className="row" style={{ marginTop: 12 }}>
        <button className="btn primary" disabled={saving} onClick={() => void save()}>
          {saving ? (row.id ? 'Saving…' : 'Adding…') : row.id ? 'Save' : 'Add'}
        </button>
        <button className="btn quiet" onClick={close}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function Line({ e, kinds }: { e: Endpoint; kinds: Record<string, string> }) {
  const { refresh } = useConsole();
  const [editing, setEditing] = useState(false);
  const state = !e.active
    ? 'Off'
    : !e.online
      ? 'Not answering'
      : e.kind === 'langfuse'
        ? e.detail || 'Answering'
        : (e.running ? 'Rendering' : 'Free') + (e.detail ? ' · ' + e.detail : '');
  return (
    <div className={css('card')}>
      <div className={css('card-head')} style={{ justifyContent: 'flex-start', gap: 10 }}>
        <span className={css('dot ' + (e.active && e.online ? 'online' : e.active ? 'offline' : ''))} />
        <h2>{e.name}</h2>
      </div>
      {/* the address in full, to read and copy at a glance */}
      {!e.url ? (
        <p className="muted small">No address yet. Edit to add one.</p>
      ) : (
        <div className={css('endpoint-url')}>
          <code>{e.url}</code>
          <button className="btn small quiet" onClick={() => void navigator.clipboard.writeText(e.url)}>
            Copy
          </button>
        </div>
      )}
      <p className="muted small">{state}</p>
      <div className="row">
        <button className="btn small" onClick={() => setEditing(true)}>
          Edit
        </button>
        <button
          className="btn small"
          onClick={() =>
            void api('/api/admin/endpoints/' + e.id, { method: 'PUT', json: { active: !e.active } }).then(
              refresh,
              failed,
            )
          }
        >
          {e.active ? 'Switch off' : 'Switch on'}
        </button>
        <button
          className="btn small quiet danger"
          onClick={() => {
            void sure(`Remove ${e.name}?`).then((yes) => {
              if (yes) void api('/api/admin/endpoints/' + e.id, { method: 'DELETE' }).then(refresh, failed);
            });
          }}
        >
          Remove
        </button>
      </div>
      {editing && <Form kinds={kinds} row={e} close={() => setEditing(false)} />}
    </div>
  );
}

export default function Servers() {
  const fresh = useRef(false); // Check again: every server is asked now, not what was found a few seconds ago
  const { refresh } = useConsole();
  const [adding, setAdding] = useState<string | null>(null); // a new one is added in its own group
  const query = useSection('endpoints', [], () => {
    const ask = api<Data>('/api/admin/endpoints' + (fresh.current ? '?fresh=1' : ''));
    fresh.current = false;
    return ask;
  });
  return (
    <Loaded query={query}>
      {(d) => (
        <>
          <div className="row">
            <p className="muted" style={{ flex: 1 }}>
              Add a server here and the studio uses it at once, no restart.
            </p>
            <button
              className="btn small"
              onClick={() => {
                fresh.current = true;
                void refresh();
              }}
            >
              Check again
            </button>
          </div>
          {Object.entries(d.kinds).map(([kind, label]) => (
            <div key={kind}>
              <div className={css('card-head')} style={{ marginTop: 18 }}>
                <h2>{label}</h2>
                <button className="btn small primary" onClick={() => setAdding(kind)}>
                  Add
                </button>
              </div>
              <p className="muted small">{ABOUT[kind]}</p>
              {adding === kind && <Form kinds={d.kinds} row={{ kind, active: 1 }} close={() => setAdding(null)} />}
              {d.endpoints
                .filter((e) => e.kind === kind)
                .map((e) => (
                  <Line key={e.id} e={e} kinds={d.kinds} />
                ))}
              {d.endpoints.some((e) => e.kind === kind) ? null : <p className="muted small">None yet.</p>}
            </div>
          ))}
        </>
      )}
    </Loaded>
  );
}
