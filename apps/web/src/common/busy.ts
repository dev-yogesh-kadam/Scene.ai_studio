// Whether the admin is in the middle of something the console should not draw over: a dialog or a drawer open, or the
// pointer on a chart. Live sections wait while it is so.

import { useEffect, useRef } from 'react';

let held = 0;

/** Says something is open; the function it returns says it closed. */
export function markBusy() {
  held += 1;
  let over = false;
  return () => {
    if (over) return;
    over = true;
    held -= 1;
  };
}

export const isBusy = () => held > 0;

/** What an element spreads on itself to count as busy while the pointer is on it or the focus is in it. */
export function useHoldWhileUsed() {
  const hover = useRef<(() => void) | null>(null);
  const focus = useRef<(() => void) | null>(null);
  useEffect(
    () => () => {
      hover.current?.();
      focus.current?.();
    },
    [],
  );
  const enter = (slot: typeof hover) => {
    slot.current ??= markBusy();
  };
  const leave = (slot: typeof hover) => {
    slot.current?.();
    slot.current = null;
  };
  return {
    onMouseEnter: () => enter(hover),
    onMouseLeave: () => leave(hover),
    onFocus: () => enter(focus),
    onBlur: () => leave(focus),
  };
}
