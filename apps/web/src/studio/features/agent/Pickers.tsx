// The choices under the message box: which model answers and how hard it thinks (ModelPicker, EffortPicker), whether a
// plan runs at once or waits (PermissionPicker), and which workflows this chat is pinned to (PinsPicker).

import { useRef } from 'react';
import { Icon } from '../../../common/components/Icon/Icon';
import { popover, s as pop } from '../../../common/components/Popover';
import { cx } from '../../../common/cx';
import { loadCatalog } from '../jobs/jobForm';
import { EFFORT_NAMES, PERMISSIONS, type AgentChat } from './chat';
import s from './Composer.module.css';

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

/** The workflows this chat uses: ticked ones are the only ones of their kind the agent plans with here. */
export function PinsPicker({ chat }: { chat: AgentChat }) {
  const button = useRef<HTMLButtonElement>(null);
  const open = async () => {
    let listed;
    try {
      listed = (await loadCatalog()).workflows.filter((w) => (w.kind === 'video' || w.kind === 'image') && !w.error);
    } catch (e) {
      chat.say((e as Error).message);
      return;
    }
    if (!button.current) return;
    const rows = listed;
    popover(
      button.current,
      (close) => (
        <>
          <div className={pop['pop-title']}>Workflows for this chat</div>
          <p className="muted small" style={{ margin: '0 10px 6px' }}>
            Tick the ones this chat uses. None ticked: the agent chooses.
          </p>
          {rows.map((w) => {
            const on = chat.chatWorkflows.includes(w.id);
            return (
              <button
                key={w.id}
                type="button"
                className={pop['pop-item']}
                role="menuitemcheckbox"
                aria-checked={on}
                onClick={() => {
                  chat.setPins(on ? chat.chatWorkflows.filter((x) => x !== w.id) : [...chat.chatWorkflows, w.id]);
                  close();
                  void open();
                }}
              >
                <Icon name={w.kind} />
                <span>
                  <b>{w.title}</b>
                  <span className="muted small">{w.kind === 'video' ? 'Video' : 'Image'}</span>
                </span>
                {on ? <Icon name="check" /> : <span />}
              </button>
            );
          })}
          {chat.chatWorkflows.length > 0 && (
            <button
              type="button"
              className={pop['pop-item']}
              onClick={() => {
                chat.setPins([]);
                close();
              }}
            >
              <Icon name="skip" />
              <span>
                <b>Let the agent choose</b>
              </span>
              <span />
            </button>
          )}
        </>
      ),
      pop['pop-perm'],
    );
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
