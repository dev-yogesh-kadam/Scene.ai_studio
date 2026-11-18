// Servers & APIs → Providers: every provider with its keys under it, the provider router's switch, which provider the
// agent uses (Claude on this PC, which has no key and gets one small card of its own: ClaudeOnThisPC), and Add key (checked with the provider before it is saved: "Works · 22 models · 91,296 credits" or the
// exact error; a key that fails is saved only on "Save anyway"). Keys are never sent back: a key shows its label and
// last 4. See backend/scene/api/providers.py, providers/registry.py and providers/router.py.

import { useEffect, useRef, useState } from 'react';
import { api } from '../../../common/api';
import { Field } from '../../../common/components/AuthForm';
import { Segmented } from '../../../common/components/Segmented';
import { classesOf } from '../../../common/cx';
import { Notice, ago, failed, sure } from '../shared/ui';
import css0 from '../../../common/components/Shared.module.css';
import css1 from '../../../common/components/Shared2.module.css';
import css2 from '../../../common/components/Shared3.module.css';
import css3 from './Servers.module.css';
import css4 from '../../../studio/pages/create/CreatePage.module.css';
import { claudeWords, type ClaudeStatus } from './claude';
import { ClaudeOnThisPC } from './ClaudeConnection';
import {
  ROUTER_WORDS,
  STATE_WORDS,
  checkWords,
  keyDot,
  keyWords,
  manyWords,
  unlockWords,
  wholeOrNull,
  type Capability,
  type Check,
  type CoverageData,
  type ManyResult,
  type Provider,
  type ProviderKey,
  type ProvidersData,
} from './providerWords';
const css = classesOf(css0, css1, css2, css3, css4);

const PATH = '/api/admin/providers';
const PLACEHOLDER: Record<string, string> = {
  scene_provider_v1: 'http://100.71.159.106:8189',
  comfyui: 'http://100.123.221.34:8188',
};
const KEY_HINT: Record<string, string> = {
  scene_provider_v1: 'sa_live_… or sa_test_…',
  comfyui: 'Empty unless a proxy in front of it wants one',
  anthropic: 'sk-ant-…',
};
const NEW = 'new:'; // a choice of the Add key form's provider list: a new provider of this kind
const CLAUDE_KINDS = ['claude_local', 'anthropic']; // what the agent's model can come from

type Props = {
  data: ProvidersData;
  claude?: ClaudeStatus; // how the agent's connection is now (/api/admin/claude-connection)
  refresh: () => Promise<void>;
};

function AddKey({ data, close, done }: { data: ProvidersData; close: () => void; done: (d: ProvidersData) => void }) {
  const keyless = data.keyless ?? [];
  const builtIn = data.built_in ?? [];
  // Claude on this PC takes no key; On this PC (the studio's own tools) has its one key already
  const keyed = data.providers.filter((p) => !keyless.includes(p.kind) && !builtIn.includes(p.kind));
  const [target, setTarget] = useState(keyed[0] ? String(keyed[0].id) : NEW + 'scene_provider_v1');
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [label, setLabel] = useState('');
  const [secret, setSecret] = useState('');
  const [most, setMost] = useState('');
  const [cap, setCap] = useState('');
  const [check, setCheck] = useState<Check | null>(null);
  const [saving, setSaving] = useState(false);
  const [several, setSeveral] = useState(false); // a paste of several keys, one a line ("Copy all" of the generation server)
  const [text, setText] = useState('');
  const [results, setResults] = useState<ManyResult[] | null>(null);
  const busy = useRef(false);
  const kind = target.startsWith(NEW)
    ? target.slice(NEW.length)
    : (data.providers.find((p) => String(p.id) === target)?.kind ?? '');
  const isNew = target.startsWith(NEW);
  const canPaste = kind === 'scene_provider_v1' || kind === 'anthropic';
  const pasting = several && canPaste;
  const save = async (anyway: boolean) => {
    if (busy.current) return;
    let json: Record<string, unknown>;
    try {
      json = pasting
        ? { text, max_concurrent: wholeOrNull(most), daily_cap: wholeOrNull(cap), save_anyway: anyway }
        : { secret, label, max_concurrent: wholeOrNull(most), daily_cap: wholeOrNull(cap), save_anyway: anyway };
    } catch (e) {
      setCheck({ ok: false, status: 'unknown', error: (e as Error).message, models: 0 });
      return;
    }
    if (isNew) Object.assign(json, { kind, name, base_url: url });
    else json.provider_id = Number(target);
    busy.current = true;
    setSaving(true);
    setCheck(null);
    try {
      if (pasting) {
        const got = await api<ProvidersData>(PATH + '/keys/many', { method: 'POST', json });
        const lines = got.results ?? [];
        setResults(lines);
        if (got.saved) done(got);
        if (got.provider_id) setTarget(String(got.provider_id)); // a new provider is made once: the rest go to it
        if (lines.every((r) => r.saved || r.words)) {
          setText('');
          if (got.saved) close();
        }
        return;
      }
      const got = await api<ProvidersData>(PATH + '/keys', { method: 'POST', json });
      setCheck(got.check ?? null);
      if (got.saved) {
        setSecret('');
        done(got);
        if (got.provider_id) setTarget(String(got.provider_id));
        if (got.check?.ok) close();
      }
    } catch (e) {
      setCheck({ ok: false, status: 'unknown', error: (e as Error).message, models: 0 });
    } finally {
      busy.current = false;
      setSaving(false);
    }
  };
  const failedLines = (results ?? []).some((r) => !r.saved && !r.words);
  return (
    <div className={css('card')} data-testid="add-key">
      {/* No autofill: a browser would put the console's sign-in email and password in the address and the key. */}
      {canPaste && (
        <div className="field">
          <Segmented
            choices={[
              { id: 'one', label: 'One key' },
              { id: 'several', label: 'Several keys' },
            ]}
            current={several ? 'several' : 'one'}
            onPick={(id) => {
              setSeveral(id === 'several');
              setCheck(null);
              setResults(null);
            }}
          />
        </div>
      )}
      <div className={css('grid2')}>
        <Field label="Provider">
          <select
            aria-label="Provider"
            value={target}
            onChange={(e) => {
              setTarget(e.target.value);
              setCheck(null);
            }}
          >
            {keyed.map((p) => (
              <option key={p.id} value={String(p.id)}>
                {p.name} ({p.kind_name})
              </option>
            ))}
            {Object.entries(data.kinds)
              .filter(([id]) => !keyless.includes(id) && !builtIn.includes(id))
              .map(([id, label]) => (
                <option key={id} value={NEW + id}>
                  New: {label}
                </option>
              ))}
          </select>
        </Field>
        {pasting ? null : (
          <Field label="Label">
            <input
              type="text"
              autoComplete="off"
              aria-label="Label"
              maxLength={60}
              placeholder="studio A"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
          </Field>
        )}
      </div>
      {isNew && (
        <div className={css('grid2')}>
          <Field label="Name">
            <input
              type="text"
              autoComplete="off"
              aria-label="Name"
              maxLength={60}
              placeholder={data.kinds[kind]}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </Field>
          {data.self_hosted.includes(kind) && (
            <Field label="Address">
              <input
                type="text"
                autoComplete="off"
                aria-label="Address"
                placeholder={PLACEHOLDER[kind]}
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
              <div className="hint">Asked once: every later key for it is only pasted.</div>
            </Field>
          )}
        </div>
      )}
      {pasting ? (
        <Field label="Keys">
          <textarea
            aria-label="Keys"
            autoComplete="off"
            spellCheck={false}
            rows={6}
            placeholder={
              'One a line: label<Tab>key, or the key alone\nScene.ai · Video · Seedance 2.5\tsa_live_…\nsa_live_…'
            }
            value={text}
            onChange={(e) => setText(e.target.value)}
            style={{ fontFamily: 'monospace', width: '100%' }}
          />
          <div className="hint">
            Paste what the generation server's “Copy all” gives. A key with no label takes the provider's label for it.
            Each key is checked before it is saved.
          </div>
        </Field>
      ) : (
        <Field label="Key">
          <input
            type="password"
            autoComplete="new-password"
            aria-label="Key"
            placeholder={KEY_HINT[kind] ?? ''}
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
          />
        </Field>
      )}
      <div className={css('grid2')}>
        <Field label="Max at once">
          <input
            type="number"
            min={1}
            max={64}
            aria-label="Max at once"
            placeholder="What the provider says"
            value={most}
            onChange={(e) => setMost(e.target.value)}
          />
        </Field>
        <Field label="Daily cap (studio credits)">
          <input
            type="number"
            min={0}
            aria-label="Daily cap"
            placeholder="None"
            value={cap}
            onChange={(e) => setCap(e.target.value)}
          />
        </Field>
      </div>
      {check && <Notice notice={{ text: checkWords(check), ok: check.ok }} />}
      {results && (
        <ul className="small" data-testid="paste-results" style={{ margin: '8px 0', paddingLeft: 18 }}>
          {results.map((r) => (
            <li key={r.line} className={r.saved || r.words ? '' : 'error'}>
              Line {r.line}
              {r.label ? ` · ${r.label}` : ''}: {manyWords(r)}
            </li>
          ))}
        </ul>
      )}
      <div className="row" style={{ marginTop: 12 }}>
        <button className="btn primary" disabled={saving} onClick={() => void save(false)}>
          {saving ? 'Checking…' : 'Save'}
        </button>
        {((check && !check.ok) || failedLines) && (
          <button className="btn" disabled={saving} onClick={() => void save(true)}>
            Save anyway
          </button>
        )}
        <button className="btn quiet" onClick={close}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function KeyLine({ k, done }: { k: ProviderKey; done: (d: ProvidersData) => void }) {
  const [editing, setEditing] = useState(false);
  const [label, setLabel] = useState(k.label);
  const [most, setMost] = useState(k.max_concurrent == null ? '' : String(k.max_concurrent));
  const [cap, setCap] = useState(k.daily_cap == null ? '' : String(k.daily_cap));
  const [said, setSaid] = useState<Check | null>(null);
  const [working, setWorking] = useState('');
  const act = async (what: string, work: () => Promise<ProvidersData>) => {
    setWorking(what);
    try {
      const got = await work();
      if (got.check) setSaid(got.check);
      done(got);
      return got;
    } catch (e) {
      failed(e);
    } finally {
      setWorking('');
    }
  };
  const change = (json: Record<string, unknown>) =>
    act('Saving…', () => api<ProvidersData>(`${PATH}/keys/${k.id}`, { method: 'PUT', json }));
  return (
    <div className={css('key-line')} data-testid={`key-${k.id}`}>
      <div className="row" style={{ gap: 8, alignItems: 'center' }}>
        <span className={css('dot ' + keyDot(k))} />
        <strong>{k.label}</strong>
        {k.last4 ? <code>…{k.last4}</code> : null}
        <span className="muted small">{keyWords(k)}</span>
        {k.fixed ? <span className={css('pill')}>Set by {k.label}</span> : null}
      </div>
      <p className="muted small">
        {k.last_used ? 'Last used ' + ago(k.last_used) : 'Not used yet'}
        {k.max_concurrent || k.said_max_concurrent ? ` · ${k.max_concurrent ?? k.said_max_concurrent} at once` : ''}
        {k.daily_cap != null ? ` · at most ${k.daily_cap.toLocaleString('en-US')} credits a day` : ''}
      </p>
      {k.unlocks?.length ? (
        <p className="small" data-testid={`unlocks-${k.id}`}>
          Unlocks {unlockWords(k.unlocks)}
        </p>
      ) : null}
      {k.last_error ? <p className="small error">{k.last_error}</p> : null}
      {k.alerts.map((a) => (
        <p key={a} className="small error">
          {a}
        </p>
      ))}
      {said && <Notice notice={{ text: checkWords(said), ok: said.ok }} />}
      <div className="row">
        <button
          className="btn small"
          disabled={!!working}
          onClick={() =>
            void act('Testing…', () => api<ProvidersData>(`${PATH}/keys/${k.id}/test`, { method: 'POST' }))
          }
        >
          {working === 'Testing…' ? working : 'Test'}
        </button>
        {k.fixed ? null : (
          <>
            <button className="btn small" disabled={!!working} onClick={() => setEditing((e) => !e)}>
              Edit
            </button>
            <button className="btn small" disabled={!!working} onClick={() => void change({ active: !k.active })}>
              {k.active ? 'Switch off' : 'Switch on'}
            </button>
            <button
              className="btn small quiet danger"
              disabled={!!working}
              onClick={() => {
                void sure(`Remove the key ${k.label}?`).then((yes) => {
                  if (yes)
                    void act('Removing…', () => api<ProvidersData>(`${PATH}/keys/${k.id}`, { method: 'DELETE' }));
                });
              }}
            >
              Remove
            </button>
          </>
        )}
      </div>
      {editing && (
        <div className={css('grid2')} style={{ marginTop: 8 }}>
          <Field label="Label">
            <input type="text" autoComplete="off" value={label} onChange={(e) => setLabel(e.target.value)} />
          </Field>
          <Field label="Max at once">
            <input type="number" min={1} max={64} value={most} onChange={(e) => setMost(e.target.value)} />
          </Field>
          <Field label="Daily cap (studio credits)">
            <input type="number" min={0} value={cap} onChange={(e) => setCap(e.target.value)} />
          </Field>
          <div className="row" style={{ alignItems: 'end' }}>
            <button
              className="btn small primary"
              onClick={() => {
                try {
                  void change({ label, max_concurrent: wholeOrNull(most), daily_cap: wholeOrNull(cap) }).then(
                    (got) => got && setEditing(false),
                  );
                } catch (e) {
                  failed(e);
                }
              }}
            >
              Save
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function ProviderCard({ p, done }: { p: Provider; done: (d: ProvidersData) => void }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(p.name);
  const [url, setUrl] = useState(p.base_url);
  const [workflows, setWorkflows] = useState('');
  const put = (json: Record<string, unknown>) =>
    api<ProvidersData>(`${PATH}/${p.id}`, { method: 'PUT', json }).then(done, failed);
  const healthy = p.keys.some((k) => k.active && k.status === 'ok');
  return (
    <div className={css('card')} data-testid={`provider-${p.id}`}>
      <div className={css('card-head')} style={{ justifyContent: 'flex-start', gap: 10 }}>
        <span className={css('dot ' + (p.active && healthy ? 'online' : p.active ? 'offline' : ''))} />
        <h2>{p.name}</h2>
        <span className="muted small">{p.kind_name}</span>
        {p.agent ? <span className={css('pill')}>The agent uses it</span> : null}
      </div>
      {p.base_url ? (
        <div className={css('endpoint-url')}>
          <code>{p.base_url}</code>
        </div>
      ) : null}
      <p className="muted small">
        {p.active ? '' : 'Off · '}
        {p.models ? `${p.models} model${p.models === 1 ? '' : 's'}` : 'No models known yet'} · {p.keys.length} key
        {p.keys.length === 1 ? '' : 's'}
      </p>
      {p.keys.map((k) => (
        <KeyLine key={k.id} k={k} done={done} />
      ))}
      <div className="row" style={{ marginTop: 8 }}>
        <button className="btn small" onClick={() => setEditing((e) => !e)}>
          Edit
        </button>
        <button className="btn small" onClick={() => void put({ active: !p.active })}>
          {p.active ? 'Switch off' : 'Switch on'}
        </button>
        <button
          className="btn small quiet danger"
          onClick={() => {
            void sure(`Remove ${p.name} and its keys?`).then((yes) => {
              if (yes) void api<ProvidersData>(`${PATH}/${p.id}`, { method: 'DELETE' }).then(done, failed);
            });
          }}
        >
          Remove
        </button>
      </div>
      {editing && (
        <div className={css('grid2')} style={{ marginTop: 8 }}>
          <Field label="Name">
            <input type="text" autoComplete="off" value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          {p.kind !== 'anthropic' && (
            <Field label="Address">
              <input type="text" autoComplete="off" value={url} onChange={(e) => setUrl(e.target.value)} />
            </Field>
          )}
          {p.kind === 'comfyui' && (
            <Field label="Workflows">
              <input
                type="text"
                autoComplete="off"
                placeholder="Kept unless you type new ones (generation_*, video/x)"
                value={workflows}
                onChange={(e) => setWorkflows(e.target.value)}
              />
            </Field>
          )}
          <div className="row" style={{ alignItems: 'end' }}>
            <button
              className="btn small primary"
              onClick={() =>
                void put({ name, base_url: url, ...(workflows.trim() ? { workflows } : {}) }).then(() =>
                  setEditing(false),
                )
              }
            >
              Save
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/** One capability's line of What makes what: who makes it now, and the switch that stops ComfyUI making it. */
function CapabilityLine({ c, set }: { c: Capability; set: (capability: string, comfyui: boolean) => void }) {
  const models = c.models.map((m) => `${m.name}${m.keys.every((k) => k.mode === 'test') ? ' (test key)' : ''}`);
  return (
    <tr data-testid={`capability-${c.capability}`}>
      <td>
        <strong>{c.words}</strong>
      </td>
      <td className="small">{models.length ? models.join(', ') : <span className="muted">No key</span>}</td>
      <td className="small">
        {c.comfy.length ? (
          <span title={c.comfy.map((w) => w.title).join('\n')}>
            {c.comfy.length} workflow{c.comfy.length === 1 ? '' : 's'}
            {c.comfyui_on ? '' : ' · off'}
          </span>
        ) : (
          <span className="muted">None</span>
        )}
      </td>
      <td className="small">
        <span className={css('pill')}>{STATE_WORDS[c.state]}</span>
      </td>
      <td className="small">
        {!c.comfy.length ? null : c.comfyui_on ? (
          <button
            className="btn small"
            disabled={!c.can_switch_off}
            title={c.why_not || 'ComfyUI stops making it: only the providers do'}
            onClick={() => set(c.capability, false)}
          >
            Stop using ComfyUI
          </button>
        ) : (
          <button className="btn small" onClick={() => set(c.capability, true)}>
            Use ComfyUI again
          </button>
        )}
        {c.comfy.length && c.comfyui_on && c.why_not ? <div className="muted small">{c.why_not}</div> : null}
      </td>
    </tr>
  );
}

/** What makes what: per capability, the providers' models and ComfyUI's workflows, and ComfyUI switched off one
 * capability at a time (only while the router is on and a live key makes it), the way off ComfyUI. */
function WhatMakesWhat({ version }: { version: unknown }) {
  const [data, setData] = useState<CoverageData | null>(null);
  const [problem, setProblem] = useState('');
  useEffect(() => {
    let live = true;
    api<CoverageData>(PATH + '/capabilities').then(
      (got) => live && (setData(got), setProblem('')),
      (e: Error) => live && setProblem(e.message),
    );
    return () => {
      live = false;
    };
  }, [version]);
  const set = (capability: string, comfyui: boolean) =>
    void api<CoverageData>(`${PATH}/capabilities/${capability}`, { method: 'PUT', json: { comfyui } }).then(
      setData,
      failed,
    );
  if (problem) return <p className="small error">What makes what could not be read: {problem}</p>;
  if (!data) return null;
  const shown = data.capabilities.filter((c) => c.models.length || c.comfy.length);
  const comfyLeft = data.capabilities.filter((c) => c.comfy.length && c.comfyui_on).length;
  return (
    <div className={css('card')} data-testid="what-makes-what" style={{ marginTop: 18 }}>
      <div className={css('card-head')}>
        <h2>What makes what</h2>
        <span className="muted small">
          {comfyLeft
            ? `ComfyUI still makes ${comfyLeft} kind${comfyLeft === 1 ? '' : 's'} of work`
            : 'ComfyUI makes nothing now'}
        </span>
      </div>
      <p className="muted small">
        Each kind of work, the providers' models that make it (from the keys above) and ComfyUI's workflows. Once a live
        key makes something and the router is on, stop using ComfyUI for it: its workflows are no longer offered in
        Create or to the agent. Switch it back on at any time.
      </p>
      <div className={css('table-wrap')}>
        <table style={{ width: '100%' }}>
          <thead>
            <tr>
              <th>Work</th>
              <th>Providers' models</th>
              <th>ComfyUI</th>
              <th>Made by now</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {shown.map((c) => (
              <CapabilityLine key={c.capability} c={c} set={set} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function ProvidersPart({ data, claude, refresh }: Props) {
  const [shown, setShown] = useState(data); // what the last change answered, until the section is asked again
  const [from, setFrom] = useState(data);
  if (from !== data) {
    setFrom(data);
    setShown(data);
  }
  const [adding, setAdding] = useState(false);
  const done = (got: ProvidersData) => {
    setShown(got);
    void refresh();
  };
  const llm = shown.providers.filter((p) => CLAUDE_KINDS.includes(p.kind));
  return (
    <>
      <div className={css('card-head')} style={{ marginTop: 18 }}>
        <h2>Providers</h2>
        <button className="btn small primary" onClick={() => setAdding(true)}>
          Add key
        </button>
      </div>
      <p className="muted small">
        Every model service is a provider with one or more keys. Add a key and its models appear by themselves; the
        router spreads jobs over healthy keys and moves on from a key that is refused.
      </p>
      <div className="field">
        <div className="label">Provider router</div>
        <Segmented
          choices={shown.modes.map((id) => ({ id, label: id[0].toUpperCase() + id.slice(1) }))}
          current={shown.router}
          onPick={(mode) =>
            void api<ProvidersData>(PATH + '/router', { method: 'PUT', json: { mode } }).then(done, failed)
          }
        />
        <div className="hint" data-testid="router-words">
          {ROUTER_WORDS[shown.router]}
        </div>
      </div>
      {llm.length > 0 && (
        <div className="field">
          <div className="label">The agent uses</div>
          <select
            aria-label="The agent uses"
            value={String(shown.agent_provider ?? '')}
            onChange={(e) =>
              void api<ProvidersData>(PATH + '/agent', {
                method: 'PUT',
                json: { provider_id: Number(e.target.value) },
              }).then(done, failed)
            }
          >
            {llm.map((p) => (
              <option key={p.id} value={String(p.id)}>
                {p.name} ({p.kind_name})
              </option>
            ))}
          </select>
          {claude ? (
            <div className="hint" data-testid="claude-status">
              {claude.online ? claudeWords(claude) : 'Not working: ' + (claude.detail || 'not checked yet')}
            </div>
          ) : null}
          {shown.testing ? (
            <p className="muted small">
              <span className={css('pill')}>{shown.testing}</span> While the agent runs on a personal Claude
              subscription, sign-up is closed and only admins can use the agent.
            </p>
          ) : null}
        </div>
      )}
      {adding && <AddKey data={shown} close={() => setAdding(false)} done={done} />}
      {shown.providers.map((p) =>
        p.keyless ? (
          <ClaudeOnThisPC
            key={p.id}
            name={p.name}
            inUse={p.agent}
            status={claude}
            testing={shown.testing}
            refresh={refresh}
          />
        ) : (
          <ProviderCard key={p.id} p={p} done={done} />
        ),
      )}
      {shown.providers.length ? null : <p className="muted small">None yet.</p>}
      <WhatMakesWhat version={shown} />
    </>
  );
}
