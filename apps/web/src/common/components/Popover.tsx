// A small menu by a button: below the button when it fits, else above; kept on screen. One at a
// time; a press outside it or Escape closes it (Escape gives the focus back to the button).

import { useEffect, useLayoutEffect, useRef, type ReactNode } from 'react';
import { Icon, type IconName } from './Icon/Icon';
import { showOverlay } from './OverlayHost';
import s from './Popover.module.css';

export { s };

export type Pop = { close: () => void };

let openPop: Pop | null = null;

/** Where a menu goes: `around`, a larger box it is centred over (the agent panel), instead of the button's left edge. */
export type PopPlace = { around?: HTMLElement | null };

function Menu({
  anchor,
  className,
  content,
  close,
  place,
}: {
  anchor: HTMLElement;
  className: string;
  content: (close: () => void) => ReactNode;
  close: () => void;
  place: PopPlace;
}) {
  const box = useRef<HTMLDivElement>(null);
  const leave = useRef(close);
  const side = useRef<'below' | 'above' | null>(null);
  useLayoutEffect(() => {
    leave.current = close;
    const node = box.current;
    if (!node) return;
    const at = anchor.getBoundingClientRect();
    const room = node.getBoundingClientRect();
    // the side is chosen once: a menu whose content grows (a new tab) grows away from its button, never off screen
    side.current ??= at.bottom + 6 + room.height < window.innerHeight ? 'below' : 'above';
    const around = place.around?.getBoundingClientRect();
    const left = around ? around.left + (around.width - room.width) / 2 : at.left;
    node.style.left = Math.max(8, Math.min(left, window.innerWidth - room.width - 8)) + 'px';
    if (side.current === 'below') {
      node.style.top = at.bottom + 6 + 'px';
      node.style.bottom = '';
    } else {
      node.style.top = '';
      node.style.bottom = window.innerHeight - at.top + 6 + 'px';
      node.style.maxHeight = Math.max(160, at.top - 14) + 'px';
    }
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

export function popover(
  anchor: HTMLElement,
  content: (close: () => void) => ReactNode,
  className = '',
  place: PopPlace = {},
): Pop {
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
  const take = showOverlay(
    <Menu anchor={anchor} className={className} content={content} close={pop.close} place={place} />,
  );
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
