// The choices under the message box: which model answers and how hard it thinks (ModelPicker, EffortPicker), whether a
// plan runs at once or waits (PermissionPicker), and which workflows this chat is pinned to (PinsPicker).

import { useRef, useState } from 'react';
import { Icon } from '../../../common/components/Icon/Icon';
import { popover, s as pop } from '../../../common/components/Popover';
import { cx } from '../../../common/cx';
import { loadCatalog, loadModelCatalog } from '../jobs/jobForm';
import { EFFORT_NAMES, PERMISSIONS, type AgentChat } from './chat';
import s from './Composer.module.css';
import { CHECK_RESULTS } from './shots';
import { clearKind, kindOfPin, pinTabs, togglePin, type PinEntry, type PinTab } from './pins';

function EffortPicker({ chat, close }: { chat: AgentChat; close: () => void }) {
  const { levels } = chat.effortsOf(chat.models.current);
  const effort = chat.effortOf(chat.models.current);
  if (!levels.length) return null;
  return (
    <div className={pop['pop-effort']}>
      <div className={pop['pop-title']}>Effort</div>
      <div className={pop['effort-levels']} role="radiogroup" aria-label="Effort">
        {levels.map((level) => (
          <button
            key={level}
            type="button"
            role="radio"
            className={cx(pop['effort-level'], level === effort && pop.on)}
            aria-checked={level === effort}
            onClick={() => {
              chat.setEffort(level);
              close();
            }}
          >
            {EFFORT_NAMES[level] || level}
          </button>
        ))}
      </div>
      <p className={cx('muted small', pop['effort-note'])}>
        Higher thinks longer before it answers: slower, and uses more tokens.
      </p>
    </div>
  );
}

export function ModelPicker({ chat }: { chat: AgentChat }) {
  const button = useRef<HTMLButtonElement>(null);
  const { models } = chat;
  const effort = chat.effortOf(models.current);
  const open = () => {
    if (!button.current) return;
    popover(
      button.current,
      (close) => (
        <>
          <div className={pop['pop-title']}>Agent model</div>
          {models.list.map((name) => (
            <button
              key={name}
              type="button"
              className={pop['pop-item']}
              role="menuitemradio"
              aria-checked={name === models.current}
              onClick={() => {
                chat.setModel(name);
                close();
              }}
            >
              <span>
                <b>{models.shown(name)}</b>
                <span className="muted small">{chat.priceText(name)}</span>
              </span>
              {name === models.current ? <Icon name="check" /> : <span />}
            </button>
          ))}
          <EffortPicker chat={chat} close={close} />
        </>
      ),
      pop['pop-perm'],
    );
  };
  return (
    <button
      ref={button}
      type="button"
      className={cx(s['agent-model-btn'], !models.list.length && 'hidden')}
      aria-haspopup="menu"
      title={
        `The model the agent uses: ${models.shown(models.current || '')} · ${chat.priceText(models.current)}` +
        (effort ? ` · Effort: ${EFFORT_NAMES[effort] || effort}` : '')
      }
      onClick={open}
    >
      <span className={s['agent-model-name']}>{models.shown(models.current || '')}</span>
      {effort && <span className={s['agent-model-effort']}>{EFFORT_NAMES[effort] || effort}</span>}
      <Icon name="down" />
    </button>
  );
}

export function PermissionPicker({ chat }: { chat: AgentChat }) {
  const button = useRef<HTMLButtonElement>(null);
  const now = chat.permission();
  const open = () => {
    if (!button.current) return;
    popover(
      button.current,
      (close) => (
        <>
          <div className={pop['pop-title']}>Generation permission</div>
          {PERMISSIONS.map((p) => (
            <button
              key={p.id}
              type="button"
              className={pop['pop-item']}
              role="menuitemradio"
              aria-checked={p.id === now.id}
              onClick={() => {
                chat.setPermission(p.id);
                close();
              }}
            >
              <Icon name={p.icon} />
              <span>
                <b>{p.label}</b>
                <span className="muted small">{p.about}</span>
              </span>
              {p.id === now.id ? <Icon name="check" /> : <span />}
            </button>
          ))}
          {/* a failed shot is found by its check: with no checks (CHECK_RESULTS) there is nothing to retry */}
          {CHECK_RESULTS && (
            <button
              type="button"
              className={pop['pop-item']}
              role="menuitemcheckbox"
              aria-checked={chat.retryOnce}
              onClick={() => {
                void chat.setRetryOnce(!chat.retryOnce);
                close();
              }}
            >
              <Icon name="retry" />
              <span>
                <b>Retry a failed shot once by itself</b>
                <span className="muted small">
                  A shot that fails its check is made again once, charged like any render. Off: you are asked.
                </span>
              </span>
              {chat.retryOnce ? <Icon name="check" /> : <span />}
            </button>
          )}
        </>
      ),
      pop['pop-perm'],
    );
  };
  return (
    <button
      ref={button}
      type="button"
      className={cx('icon-btn', s['agent-perm'])}
      aria-haspopup="menu"
      title={'Generation permission: ' + now.label}
      aria-label={'Generation permission: ' + now.label}
      onClick={open}
    >
      <Icon name={now.icon} />
    </button>
  );
}

/** The menu of PinsPicker: a tab for each kind, "Agent selects" first, then the generation server's models one by
 * one, then ComfyUI's workflows. Ticking keeps the menu open; the chat keeps the pins (chat.setPins). */
function PinsMenu({ chat, tabs, close }: { chat: AgentChat; tabs: PinTab[]; close: () => void }) {
  const [pins, setPinsHere] = useState(chat.chatWorkflows);
  const [kind, setKind] = useState(
    () =>
      tabs.find((t) => pins.some((p) => kindOfPin(p) === t.kind))?.kind ??
      (tabs.find((t) => t.kind === 'video') || tabs[0])?.kind,
  );
  const tab = tabs.find((t) => t.kind === kind) || tabs[0];
  const keep = (next: string[]) => {
    setPinsHere(next);
    chat.setPins(next);
  };
  if (!tab) return <p className="muted small">No workflows can be used yet.</p>;
  const chosen = pins.filter((p) => kindOfPin(p) === tab.kind);
  const row = (e: PinEntry) => {
    const on = pins.includes(e.value);
    return (
      <button
        key={e.value}
        type="button"
        className={cx(pop['pop-item'], s['pin-row'])}
        role="menuitemcheckbox"
        aria-checked={on}
        onClick={() => keep(togglePin(pins, e.value))}
      >
        <i className={cx(s['pin-box'], on && s.on)} aria-hidden>
          {on && <Icon name="check" />}
        </i>
        <span className={s['pin-text']}>
          <b>{e.title}</b>
          {e.about && <span className={s['pin-about']}>{e.about}</span>}
          {(e.sound || e.meta.length > 0) && (
            <span className={s['pin-meta']}>
              {e.sound && <Icon name="audio" />}
              {e.meta.join(' · ')}
            </span>
          )}
        </span>
      </button>
    );
  };
  return (
    <>
      <div className={pop['pop-title']}>Workflows for this chat</div>
      <div className={s['pin-tabs']} role="tablist" aria-label="Kind">
        {tabs.map((t) => {
          const count = pins.filter((p) => kindOfPin(p) === t.kind).length;
          return (
            <button
              key={t.kind}
              type="button"
              role="tab"
              aria-selected={t.kind === tab.kind}
              className={cx(s['pin-tab'], t.kind === tab.kind && s.on)}
              onClick={() => setKind(t.kind)}
            >
              <Icon name={t.icon} />
              {t.label}
              {count > 0 && <span className={s['pin-count']}>{count}</span>}
            </button>
          );
        })}
      </div>
      <button
        type="button"
        className={cx(pop['pop-item'], s['pin-row'], s['pin-auto'])}
        role="menuitemradio"
        aria-checked={!chosen.length}
        onClick={() => keep(clearKind(pins, tab.kind))}
      >
        <i className={cx(s['pin-radio'], !chosen.length && s.on)} aria-hidden />
        <span className={s['pin-text']}>
          <b>
            Agent selects <span className={s['pin-badge']}>Recommended</span>
          </b>
          <span className={s['pin-about']}>
            {chosen.length
              ? `Pick this to let the agent choose the ${tab.label.toLowerCase()} again`
              : `The agent picks the ${tab.label.toLowerCase()} model for each step`}
          </span>
        </span>
      </button>
      <div className={s['pin-list']}>
        {tab.models.length > 0 && <div className={s['pin-section']}>Models (generation server)</div>}
        {tab.models.map(row)}
        {tab.workflows.length > 0 && <div className={s['pin-section']}>Workflows (ComfyUI)</div>}
        {tab.workflows.map(row)}
      </div>
      {pins.length > 0 && (
        <button
          type="button"
          className={cx(pop['pop-item'], s['pin-clear'])}
          onClick={() => {
            keep([]);
            close();
          }}
        >
          <Icon name="skip" />
          <span>
            <b>Let the agent choose everything</b>
          </span>
        </button>
      )}
    </>
  );
}

/** The workflows and models this chat uses: ticked ones are the only ones of their kind the agent plans with here. */
export function PinsPicker({ chat }: { chat: AgentChat }) {
  const button = useRef<HTMLButtonElement>(null);
  const open = async () => {
    let tabs: PinTab[];
    try {
      const [catalog, models] = await Promise.all([
        loadCatalog(),
        loadModelCatalog().catch(() => ({ models: {} })), // without the server's list the presets still name them
      ]);
      tabs = pinTabs(catalog.workflows, models.models);
    } catch (e) {
      chat.say((e as Error).message);
      return;
    }
    if (!button.current) return;
    popover(button.current, (close) => <PinsMenu chat={chat} tabs={tabs} close={close} />, s['pin-pop']);
  };
  const title = chat.chatWorkflows.length
    ? `Workflows for this chat: ${chat.chatWorkflows.length} chosen`
    : 'Workflows for this chat: the agent chooses';
  return (
    <button
      ref={button}
      type="button"
      className={cx('icon-btn', s['agent-pins'])}
      aria-haspopup="menu"
      title={title}
      aria-label={title}
      style={{ color: chat.chatWorkflows.length ? 'var(--accent, #f5c542)' : undefined }}
      onClick={() => void open()}
    >
      <Icon name="sliders" />
    </button>
  );
}
