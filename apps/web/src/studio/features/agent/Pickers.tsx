// The choices under the message box: the model picker (ModelPicker: the agent's own model and its effort on the Chat
// tab, and the image / video / audio models this chat is pinned to on the others), and whether a plan runs at once or
// waits (PermissionPicker).

import { useRef, useState } from 'react';
import { Icon, type IconName } from '../../../common/components/Icon/Icon';
import { popover, s as pop } from '../../../common/components/Popover';
import { cx } from '../../../common/cx';
import { loadCatalog } from '../jobs/jobForm';
import { EFFORT_NAMES, PERMISSIONS, type AgentChat } from './chat';
import s from './Composer.module.css';
import { CHECK_RESULTS } from './shots';
import { PIN_KINDS, clearKind, kindOfPin, pinTabs, togglePin, type PinEntry, type PinTab } from './pins';

/** One line on each effort level, in the effort flyout. */
const EFFORT_ABOUT: Record<string, string> = {
  low: 'Fastest, lightest reasoning effort.',
  medium: 'Balanced effort — the everyday default.',
  high: 'Deeper reasoning for hard tasks.',
  xhigh: 'Maximum effort, slowest responses.',
  max: 'Absolute maximum effort.',
};

/** One line on each Claude model family, in the Chat tab. */
const CHAT_ABOUT: [RegExp, string][] = [
  [/opus/i, 'Most capable, for complex films and long plans.'],
  [/sonnet/i, 'Best balance of speed and intelligence.'],
  [/haiku/i, 'Fastest, for quick edits and short answers.'],
  [/fable/i, 'The most capable model, for the hardest work.'],
];
const chatAbout = (name: string) => CHAT_ABOUT.find(([re]) => re.test(name))?.[1] || '';

type Flyout = { name: string; top: number; side: boolean };

/** The Chat tab: the agent's models, each with a › that opens its effort levels beside the menu. */
function ChatPane({ chat, close }: { chat: AgentChat; close: () => void }) {
  const { models } = chat;
  const [fly, setFly] = useState<Flyout | null>(null);
  /** Beside the menu when there is room on its left; else under the row, and only on a click (not on hover). */
  const openFly = (name: string, row: HTMLElement, hover = false) => {
    const box = row.closest(`.${s['model-pop']}`) as HTMLElement | null;
    if (!box) return;
    const at = row.getBoundingClientRect();
    const frame = box.getBoundingClientRect();
    const side = frame.left > 290;
    if (hover && !side) return;
    setFly({ name, top: at.top - frame.top, side });
  };
  const flyout = (name: string) => {
    const { levels, default: recommended } = chat.effortsOf(name);
    const effort = name === models.current ? chat.effortOf(name) : '';
    return (
      <div
        className={cx(s['effort-fly'], fly?.side && s.side)}
        style={fly?.side ? { top: fly.top } : undefined}
        role="menu"
        aria-label={`Effort for ${models.shown(name)}`}
      >
        {levels.map((level) => (
          <button
            key={level}
            type="button"
            role="menuitemradio"
            aria-checked={level === effort}
            className={cx(pop['pop-item'], s['pin-row'])}
            onClick={() => {
              if (name !== models.current) chat.setModel(name);
              chat.setEffort(level);
              close();
            }}
          >
            <i className={cx(s['pin-box'], level === effort && s.on)} aria-hidden>
              {level === effort && <Icon name="check" />}
            </i>
            <span className={s['model-tile']} aria-hidden>
              <Icon name="gem" />
            </span>
            <span className={s['pin-text']}>
              <b>
                {EFFORT_NAMES[level] || level}
                {level === recommended && <span className={s['pin-badge']}>Recommended</span>}
              </b>
              {EFFORT_ABOUT[level] && <span className={s['pin-about']}>{EFFORT_ABOUT[level]}</span>}
            </span>
          </button>
        ))}
      </div>
    );
  };
  return (
    <div className={s['pin-list']} onScroll={() => setFly(null)}>
      {models.list.map((name) => {
        const on = name === models.current;
        const hasLevels = chat.effortsOf(name).levels.length > 0;
        return (
          <div key={name}>
            <div className={cx(s['chat-row'], on && s.current)}>
              <button
                type="button"
                className={cx(pop['pop-item'], s['pin-row'])}
                role="menuitemradio"
                aria-checked={on}
                onMouseEnter={(e) => hasLevels && openFly(name, e.currentTarget.parentElement as HTMLElement, true)}
                onClick={() => {
                  chat.setModel(name);
                  close();
                }}
              >
                <span className={s['model-tile']} aria-hidden>
                  <Icon name="gem" />
                </span>
                <span className={s['pin-text']}>
                  <b>{models.shown(name)}</b>
                  {chatAbout(name) && <span className={s['pin-about']}>{chatAbout(name)}</span>}
                  <span className={s['pin-meta']}>{chat.priceText(name)}</span>
                </span>
              </button>
              {hasLevels && (
                <button
                  type="button"
                  className={cx('icon-btn', s['chat-more'])}
                  aria-label={`Effort for ${models.shown(name)}`}
                  aria-expanded={fly?.name === name}
                  onClick={(e) =>
                    fly?.name === name ? setFly(null) : openFly(name, e.currentTarget.parentElement as HTMLElement)
                  }
                >
                  <Icon name="right" />
                </button>
              )}
            </div>
            {fly?.name === name && !fly.side && flyout(name)}
          </div>
        );
      })}
      {fly?.side && flyout(fly.name)}
    </div>
  );
}

/** An Image / Video / Audio tab: "Agent selects" first, then the providers' models, Featured ones first. Ticking keeps
 * the menu open; the chat keeps the pins (chat.setPins). */
function KindPane({
  tab,
  pins,
  keep,
  close,
}: {
  tab: PinTab;
  pins: string[];
  keep: (next: string[]) => void;
  close: () => void;
}) {
  const chosen = pins.filter((p) => kindOfPin(p) === tab.kind);
  const featured = tab.models.filter((m) => m.featured);
  const rest = tab.models.filter((m) => !m.featured);
  const icon = PIN_KINDS.find((k) => k.id === tab.kind)?.icon || 'gem';
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
        <span className={s['model-tile']} aria-hidden>
          <Icon name={icon} />
        </span>
        <span className={s['pin-text']}>
          <b>
            {e.title}
            {e.isNew && <span className={cx(s['pin-badge'], s['badge-new'])}>NEW</span>}
          </b>
          {e.about && <span className={s['pin-about']}>{e.about}</span>}
          {(e.sound || e.meta.length > 0) && (
            <span className={s['pin-meta']}>
              {e.sound && <Icon name="audio" />}
              {e.sound && e.meta.length > 0 && '·'}
              {e.meta.join(' · ')}
            </span>
          )}
        </span>
      </button>
    );
  };
  return (
    <>
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
        {featured.length > 0 && <div className={s['pin-section']}>Featured</div>}
        {featured.map(row)}
        {rest.length > 0 && <div className={s['pin-section']}>{featured.length ? 'All models' : 'Models'}</div>}
        {rest.map(row)}
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
            <b>Let the agent choose every model</b>
          </span>
        </button>
      )}
    </>
  );
}

/** The model picker: a Chat tab for the agent's own model and effort, then a tab for each kind it makes. */
function ModelMenu({ chat, tabs, close }: { chat: AgentChat; tabs: PinTab[]; close: () => void }) {
  const [pins, setPinsHere] = useState(chat.chatWorkflows);
  const [kind, setKind] = useState('chat');
  const keep = (next: string[]) => {
    setPinsHere(next);
    chat.setPins(next);
  };
  const tab = tabs.find((t) => t.kind === kind);
  const all = [{ kind: 'chat', label: 'Chat', icon: 'chat' }, ...tabs];
  return (
    <>
      <div className={s['pin-tabs']} role="tablist" aria-label="Kind">
        {all.map((t) => {
          const count = pins.filter((p) => kindOfPin(p) === t.kind).length;
          const on = t.kind === (tab?.kind || 'chat');
          return (
            <button
              key={t.kind}
              type="button"
              role="tab"
              aria-selected={on}
              className={cx(s['pin-tab'], on && s.on)}
              onClick={() => setKind(t.kind)}
            >
              <Icon name={t.icon as IconName} />
              {t.label}
              {count > 0 && <span className={s['pin-count']}>{count}</span>}
            </button>
          );
        })}
      </div>
      {tab ? (
        <KindPane tab={tab} pins={pins} keep={keep} close={close} />
      ) : (
        <ChatPane chat={chat} close={close} />
      )}
    </>
  );
}

export function ModelPicker({ chat }: { chat: AgentChat }) {
  const button = useRef<HTMLButtonElement>(null);
  const { models } = chat;
  const effort = chat.effortOf(models.current);
  const pinned = chat.chatWorkflows.length;
  const open = async () => {
    let tabs: PinTab[] = [];
    try {
      tabs = pinTabs((await loadCatalog()).workflows);
    } catch {
      // no catalog: the Chat tab alone
    }
    if (!button.current) return;
    popover(button.current, (close) => <ModelMenu chat={chat} tabs={tabs} close={close} />, cx(s['pin-pop'], s['model-pop']));
  };
  const label =
    `Models: ${models.shown(models.current || '')}` +
    (effort ? `, effort ${EFFORT_NAMES[effort] || effort}` : '') +
    (pinned ? `, ${pinned} chosen for this chat` : ', the agent chooses the rest');
  return (
    <button
      ref={button}
      type="button"
      className={cx(s['agent-model-btn'], !models.list.length && 'hidden')}
      aria-haspopup="menu"
      title={label}
      aria-label={label}
      onClick={() => void open()}
    >
      <span className={s['agent-model-name']}>{models.shown(models.current || '')}</span>
      {effort && <span className={s['agent-model-effort']}>{EFFORT_NAMES[effort] || effort}</span>}
      {pinned > 0 && <span className={s['pin-count']}>{pinned}</span>}
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
