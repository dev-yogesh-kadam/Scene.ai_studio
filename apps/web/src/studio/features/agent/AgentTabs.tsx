// The agent's tabs: several conversations in one project, each kept on its own. A strip of tabs over the panel (rename
// one with a double-click, close it with ×, + for a new one), a history menu with every conversation, how long ago it
// was used and what it spent, and full screen: the conversation over the whole canvas.

import { forwardRef, useEffect, useId, useImperativeHandle, useMemo, useRef, useState } from 'react';
import { ask } from '../../../common/components/Dialog';
import { Icon } from '../../../common/components/Icon/Icon';
import { popover, s as pop } from '../../../common/components/Popover';
import { cx } from '../../../common/cx';
import type { Item } from '../../../common/media/item';
import { AgentPanel, type PanelHandle } from './AgentPanel';
import { SpendCard } from './Message';
import { useAgentIndex, type TabRow } from './useAgentIndex';
import s from './AgentTabs.module.css';

function age(time: number) {
  const sec = Math.max(0, (Date.now() - (time || 0)) / 1000);
  if (sec < 60) return 'just now';
  if (sec < 3600) return `${Math.round(sec / 60)} min ago`;
  if (sec < 86400) return `${Math.round(sec / 3600)} h ago`;
  const days = Math.round(sec / 86400);
  return days === 1 ? 'yesterday' : `${days} days ago`;
}

export type AgentHandle = { attach: (item: Item) => void; focus: () => void; setFull: (on: boolean) => void };

type Props = {
  project: number;
  selection: Item[];
  pick: (onPick: (items: Item[]) => void) => void;
  onUploaded: () => void;
  onJobs: (ids: string[]) => void;
  onFocus: (id: number) => void;
  locate: (id: number) => { shot: string; take: number } | null;
  onFull: (on: boolean) => void;
  focus: number; // changes when the panel asks the conversation to take the focus
};

function Spend({ t }: { t: TabRow }) {
  const [over, setOver] = useState<HTMLElement | null>(null);
  const spent = t.spent?.total || 0;
  const show = (e: { currentTarget: HTMLElement }) => setOver(e.currentTarget);
  return (
    <span
      className={s['agent-spend']}
      tabIndex={0}
      aria-label={`${spent} credits spent`}
      onPointerEnter={show}
      onFocus={show}
      onPointerLeave={() => setOver(null)}
      onBlur={() => setOver(null)}
    >
      {String(spent)}
      <i className={s.coin} aria-hidden="true" />
      {over && <SpendCard anchor={over} spent={t.spent || { total: 0 }} />}
    </span>
  );
}

export const AgentTabs = forwardRef<AgentHandle, Props>(function AgentTabs(props, ref) {
  const { project, selection, pick, onUploaded, onJobs, onFocus, locate, onFull, focus } = props;
  const tabs = useAgentIndex(project);
  const { index } = tabs;
  const [full, setFull] = useState(false);
  const [naming, setNaming] = useState<string | null>(null);
  const panels = useRef(new Map<string, PanelHandle>());
  const jobsOf = useRef(new Map<string, string[]>());
  const history = useRef<HTMLButtonElement>(null);
  const active = () => (index.active ? panels.current.get(index.active) : undefined);
  const full2 = (on: boolean) => {
    setFull(on);
    onFull(on);
  };
  useImperativeHandle(ref, () => ({
    attach: (item) => active()?.attach(item),
    focus: () => active()?.focus(),
    setFull: (on) => {
      if (on !== full) full2(on);
    },
  }));
  // A tab shown, or the panel opened on the agent: its message box has the cursor.
  useEffect(() => {
    if (index.active) panels.current.get(index.active)?.focus();
  }, [index.active, focus]);
  const row = useMemo(() => new Map(index.tabs.map((t) => [t.id, t])), [index.tabs]);
  const openTabs = index.open.map((id) => row.get(id)).filter((t): t is TabRow => !!t);
  const tabId = useId() + 'tab-';

  const openHistory = () => {
    if (!history.current) return;
    const rows = [...index.tabs].sort((a, b) => (b.updated || 0) - (a.updated || 0));
    popover(
      history.current,
      (close) => (
        <>
          <button
            type="button"
            className={pop['pop-item']}
            onClick={() => {
              close();
              tabs.addTab();
            }}
          >
            <Icon name="plus" />
            <b>New conversation</b>
          </button>
          <div className={pop['menu-sep']} />
          <div className={pop['pop-title']}>History</div>
          {rows.map((t) => (
            <div key={t.id} className={cx(s['agent-history-row'], t.id === index.active && s.on)}>
              <button
                type="button"
                className={s['agent-history-open']}
                onClick={() => {
                  close();
                  tabs.show(t.id);
                }}
              >
                <b>{t.name}</b>
                <span className="muted small">{age(t.updated) + (index.open.includes(t.id) ? '' : ' · closed')}</span>
              </button>
              <span className={s['agent-history-tools']}>
                <button
                  type="button"
                  className="icon-btn small"
                  title="Rename"
                  aria-label={`Rename ${t.name}`}
                  onClick={() => {
                    close();
                    tabs.show(t.id);
                    setNaming(t.id);
                  }}
                >
                  <Icon name="pencil" />
                </button>
                <button
                  type="button"
                  className="icon-btn small"
                  title="Delete this conversation"
                  aria-label={`Delete ${t.name}`}
                  onClick={() => {
                    void ask({
                      title: `Delete "${t.name}"?`,
                      danger: true,
                      confirm: 'Delete conversation',
                      message:
                        'Its messages and plans are removed. What it made stays on the canvas and in the library.',
                    }).then((sure) => {
                      if (!sure) return;
                      close();
                      panels.current.delete(t.id);
                      jobsOf.current.delete(t.id);
                      tabs.remove(t.id);
                    });
                  }}
                >
                  <Icon name="trash" />
                </button>
              </span>
              <Spend t={t} />
            </div>
          ))}
        </>
      ),
      pop['pop-history'],
    );
  };

  return (
    <div className={cx(s['agent-tabs'], full && s.full)}>
      <div className={s['agent-tabs-bar']}>
        <button
          ref={history}
          type="button"
          className={s['agent-history-btn']}
          aria-haspopup="menu"
          title="All conversations"
          aria-label="All conversations"
          onClick={openHistory}
        >
          <Icon name="chat" />
          <Icon name="menu" />
        </button>
        {/* The tabs' list: it owns the tab names (aria-owns), not the close buttons beside them, which stay buttons. */}
        <div
          className={s['tab-owner']}
          role="tablist"
          aria-label="Agent conversations"
          aria-owns={openTabs.map((t) => tabId + t.id).join(' ')}
        />
        <div className={s['agent-tab-list']}>
          {openTabs.map((t) => (
            <div
              key={t.id}
              ref={
                t.id === index.active
                  ? (node) => node?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
                  : undefined
              }
              className={cx(s['agent-tab'], t.id === index.active && s.on)}
              role="presentation"
              title={t.name + ' · double-click to rename'}
              onClick={() => t.id !== index.active && tabs.show(t.id)}
              onDoubleClick={() => setNaming(t.id)}
            >
              {/* the tab is its name; its close button sits beside it, not in it */}
              <span
                id={tabId + t.id}
                className={s['agent-tab-name']}
                role="tab"
                aria-selected={t.id === index.active}
                tabIndex={t.id === index.active ? 0 : -1}
                onKeyDown={(e) => {
                  if (e.key === 'F2') setNaming(t.id);
                  if (e.key === 'Enter' || e.key === ' ') tabs.show(t.id);
                }}
              >
                {naming === t.id ? (
                  <NameBox
                    t={t}
                    onDone={(name) => {
                      setNaming(null);
                      if (name) tabs.change(t.id, { name });
                    }}
                  />
                ) : (
                  t.name
                )}
              </span>
              <button
                type="button"
                className={s['agent-tab-close']}
                title="Close (it stays in the history)"
                aria-label={`Close ${t.name}`}
                onClick={(e) => {
                  e.stopPropagation();
                  tabs.close(t.id);
                }}
              >
                ×
              </button>
            </div>
          ))}
        </div>
        <button
          type="button"
          className={cx('icon-btn', s['agent-tab-add'])}
          title="New conversation"
          aria-label="New conversation"
          onClick={tabs.addTab}
        >
          <Icon name="plus" />
        </button>
        <span className={s['agent-tabs-gap']} />
        <button
          type="button"
          className={cx('icon-btn', s['agent-full-btn'])}
          title={full ? 'Exit full screen' : 'Full screen'}
          aria-label={full ? 'Exit full screen' : 'Full screen'}
          aria-pressed={full}
          onClick={() => {
            full2(!full);
            active()?.focus();
          }}
        >
          <Icon name={full ? 'shrink' : 'expand'} />
        </button>
      </div>
      <div className={s['agent-tabs-body']}>
        {tabs.seen
          .filter((id) => row.has(id))
          .map((id) => (
            <AgentPanel
              key={id}
              ref={(panel) => {
                if (panel) panels.current.set(id, panel);
                else panels.current.delete(id);
              }}
              hidden={id !== index.active}
              session={id}
              project={project}
              tabName={() => row.get(id)?.name ?? ''}
              selection={() => selection}
              selectionNow={id === index.active ? selection : []}
              pick={pick}
              onUploaded={onUploaded}
              onFocus={onFocus}
              locate={locate}
              onJobs={(ids) => {
                jobsOf.current.set(id, ids);
                onJobs([...new Set([...jobsOf.current.values()].flat())]);
              }}
              onSaved={(saved) => tabs.saved(id, saved)}
            />
          ))}
      </div>
    </div>
  );
});

/** Rename in place: Enter or leaving it keeps the new name, Escape keeps the old one. */
function NameBox({ t, onDone }: { t: TabRow; onDone: (name: string | null) => void }) {
  const ended = useRef(false);
  const end = (name: string | null) => {
    if (ended.current) return;
    ended.current = true;
    onDone(name);
  };
  return (
    <input
      type="text"
      className={s['agent-tab-name-edit']}
      defaultValue={t.name}
      maxLength={40}
      aria-label="Name of the conversation"
      ref={(input) => input?.select()}
      onKeyDown={(e) => {
        e.stopPropagation();
        if (e.key === 'Enter') end(e.currentTarget.value.trim());
        if (e.key === 'Escape') end(null);
      }}
      onBlur={(e) => end(e.currentTarget.value.trim())}
      onClick={(e) => e.stopPropagation()}
    />
  );
}
