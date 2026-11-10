// Where what opens over the page is drawn: windows, menus and the viewer. They are asked for from anywhere (ask(),
// openDialog(), popover(), openViewer()); the host, placed once at the root of each app, draws them on <body>.

import { Fragment, useSyncExternalStore, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

type Entry = { id: number; node: ReactNode };

let entries: Entry[] = [];
let nextId = 0;
const listeners = new Set<() => void>();
const changed = () => listeners.forEach((listener) => listener());
const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

/** Puts something over the page; the function it returns takes it away. */
export function showOverlay(node: ReactNode) {
  const id = ++nextId;
  entries = [...entries, { id, node }];
  changed();
  return () => {
    entries = entries.filter((e) => e.id !== id);
    changed();
  };
}

export function OverlayHost() {
  const shown = useSyncExternalStore(subscribe, () => entries);
  return createPortal(
    shown.map((e) => <Fragment key={e.id}>{e.node}</Fragment>),
    document.body,
  );
}
