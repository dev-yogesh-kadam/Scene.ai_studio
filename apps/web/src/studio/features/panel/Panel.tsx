// The panel on the right of the canvas: Quick actions, the Agent, NeuralCore and (for an admin) Bulk generation, one
// at a time. It is open every time the canvas is entered and remembers which tab was showing; its left edge is a grip
// (drag it to make the panel wider or narrower, double-click for the usual width); Ctrl or ⌘ + J shows or hides it.
// Every tab stays mounted while another shows: a form keeps what was typed, a reply keeps streaming.

import { useCallback, useEffect, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react';
import { Icon, type IconName } from '../../../common/components/Icon/Icon';
import { Segmented } from '../../../common/components/Segmented';
import { cx } from '../../../common/cx';
import { prefs } from '../../../common/prefs';
import { KIT } from '../../words';
import { track } from '../../pages/canvas/camera';
import s from './Panel.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../Shared.module.css';
const css = classesOf(css0);

export type Tab = 'quick' | 'agent' | 'kit' | 'bulk';

const TABS: { id: Tab; label: string; icon: IconName; admin?: boolean }[] = [
  { id: 'quick', label: 'Quick actions', icon: 'bolt' },
  { id: 'agent', label: 'Agent', icon: 'chat' },
  { id: 'kit', label: KIT, icon: 'memory' },
  { id: 'bulk', label: 'Bulk generation', icon: 'grid', admin: true },
];
export const PANEL = 380; // the width the panel starts with
const PANEL_MIN = 320;
const PANEL_MAX = 960;

/**
 * The tab the panel opens on: the Agent, unless another tab was showing last time (Bulk: an admin's). Kept under its
 * own key since the Agent became the first tab: the old key holds "quick" for everyone who opened the panel when Quick
 * actions was the first, and would keep them there.
 */
const TAB_KEY = 'scene.panel.last-tab';
function savedTab(admin: boolean): Tab {
  const saved = prefs.get(TAB_KEY);
  if (saved === 'quick') return 'quick';
  if (saved === 'kit' || saved === 'memory') return 'kit';
  if (saved === 'bulk' && admin) return 'bulk';
  return 'agent';
}

/** The panel's state: open, which tab, how wide (clamped to the room the page has). */
export function usePanel(admin: boolean, room: () => number) {
  const [open, setOpen] = useState(true);
  const [tab, setTab] = useState<Tab>(() => savedTab(admin));
  const clampWidth = useCallback(
    (width: number) =>
      Math.min(Math.max(Math.round(width) || PANEL, PANEL_MIN), Math.max(PANEL_MIN, Math.min(PANEL_MAX, room() - 280))),
    [room],
  );
  const [width, setWidth] = useState(() => clampWidth(Number(prefs.get('scene.panel.width'))));
  const [focus, setFocus] = useState(0); // asks the tab shown to take the focus
  const show = useCallback((next: boolean, which?: Tab) => {
    setOpen(next);
    if (which) setTab(which);
    if (next) setFocus((n) => n + 1);
  }, []);
  useEffect(() => prefs.set(TAB_KEY, tab), [tab]); // remembered as it is shown
  return {
    open,
    tab,
    width,
    focus,
    show,
    resize: (w: number) => setWidth(clampWidth(w)),
    keep: (w: number) => prefs.set('scene.panel.width', String(clampWidth(w))),
  };
}

type Props = {
  tab: Tab;
  admin: boolean;
  width: number;
  onTab: (tab: Tab) => void;
  onClose: () => void;
  onResize: (width: number) => void;
  onResized: (width: number) => void; // the drag ended: the width is kept
  onResizing: (on: boolean) => void;
  tabs: Record<Tab, ReactNode>;
};

export function Panel({ tab, admin, width, onTab, onClose, onResize, onResized, onResizing, tabs }: Props) {
  const shown = TABS.filter((t) => !t.admin || admin);
  const title = TABS.find((t) => t.id === tab)?.label ?? '';
  const grip = (e: ReactPointerEvent) => {
    if (e.button !== 0) return;
    e.preventDefault();
    const from = { x: e.clientX, width };
    let last = width;
    onResizing(true);
    track(
      (ev) => {
        last = from.width + from.x - ev.clientX;
        onResize(last);
      },
      () => {
        onResizing(false);
        onResized(last);
      },
    );
  };
  return (
    <aside className={s['side-panel']} aria-label="Make something">
      <div
        className={s['panel-grip']}
        title="Drag to resize. Double-click for the usual width."
        role="separator"
        aria-orientation="vertical"
        onDoubleClick={() => {
          onResize(PANEL);
          onResized(PANEL);
        }}
        onPointerDown={grip}
      />
      <div className={s['panel-head']}>
        <b className={css(cx(s['panel-title'], tab === 'agent' && s['agent-name']))}>{title}</b>
        <span style={{ flex: 1 }} />
        <Segmented
          className={s.tabs}
          choices={shown.map((t) => ({ id: t.id, label: <Icon name={t.icon} />, hint: t.label }))}
          current={tab}
          onPick={onTab}
        />
        <button className="icon-btn" title="Close (Ctrl or ⌘ + J)" aria-label="Close the panel" onClick={onClose}>
          ×
        </button>
      </div>
      {(Object.keys(tabs) as Tab[])
        .filter((id) => id !== 'bulk' || admin)
        .map((id) => (
          <div key={id} className={cx(id === 'bulk' ? s['panel-bulk'] : s['panel-quick'], id !== tab && 'hidden')}>
            {tabs[id]}
          </div>
        ))}
    </aside>
  );
}
