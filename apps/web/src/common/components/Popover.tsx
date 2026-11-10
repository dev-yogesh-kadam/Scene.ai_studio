// A small menu by a button: below the button when it fits, else above; kept on screen. One at a
// time; a press outside it or Escape closes it (Escape gives the focus back to the button).

import { useEffect, useLayoutEffect, useRef, type ReactNode } from 'react';
import { Icon, type IconName } from './Icon/Icon';
import { showOverlay } from './OverlayHost';
import s from './Popover.module.css';

export { s };

export type Pop = { close: () => void };

let openPop: Pop | null = null;

function Menu({
  anchor,
  className,
  content,
  close,
}: {
  anchor: HTMLElement;
  className: string;
  content: (close: () => void) => ReactNode;
  close: () => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const leave = useRef(close);
  useLayoutEffect(() => {
    leave.current = close;
    const node = box.current;
    if (!node) return;
    const at = anchor.getBoundingClientRect();
    const room = node.getBoundingClientRect();
    const below = at.bottom + 6 + room.height < window.innerHeight;
    node.style.left = Math.max(8, Math.min(at.left, window.innerWidth - room.width - 8)) + 'px';
    node.style.top = (below ? at.bottom + 6 : Math.max(8, at.top - room.height - 6)) + 'px';
  });
  useEffect(() => {
    const outside = (e: PointerEvent) => {
      if (!box.current?.contains(e.target as Node) && !anchor.contains(e.target as Node)) leave.current();
    };
    const escape = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      e.stopPropagation();
      leave.current();
      anchor.focus();
    };
    document.addEventListener('pointerdown', outside, true);
    document.addEventListener('keydown', escape, true);
    return () => {
      document.removeEventListener('pointerdown', outside, true);
      document.removeEventListener('keydown', escape, true);
    };
  }, [anchor]);
  return (
    <div ref={box} className={s.pop + (className ? ' ' + className : '')} role="menu">
      {content(close)}
    </div>
  );
}

export function popover(anchor: HTMLElement, content: (close: () => void) => ReactNode, className = ''): Pop {
  openPop?.close();
  let open = true;
  const pop: Pop = {
    close() {
      if (!open) return;
      open = false;
      if (openPop === pop) openPop = null;
      take();
    },
  };
  const take = showOverlay(<Menu anchor={anchor} className={className} content={content} close={pop.close} />);
  openPop = pop;
  return pop;
}

export type AddRow = { icon: IconName; label: string; hint?: string; run: () => void };

/** The "+" menu of a message box or a reference slot: where to take a file from. */
export function addMenu(anchor: HTMLElement, rows: AddRow[]) {
  return popover(
    anchor,
    (close) =>
      rows.map((row, i) => (
        <button
          key={row.label}
          type="button"
          autoFocus={i === 0}
          className={s['pop-item'] + ' ' + s['add-menu-item']}
          role="menuitem"
          onClick={() => {
            close();
            row.run();
          }}
        >
          <Icon name={row.icon} />
          <span className="grow">{row.label}</span>
          {row.hint && <span className={s['add-menu-hint']}>{row.hint}</span>}
        </button>
      )),
    s['add-menu'],
  );
}
