// The reel under the monitor: on a wide screen, how far the page has scrolled through it folds the monitor into the
// corner (0 full, 1 folded) and lays the shots out under it; elsewhere it is a plain section after the monitor.

import { useEffect, useState, type RefObject } from 'react';
import { calmNow } from '../../../common/landing/words';

const canRun = () => !calmNow() && window.innerWidth >= 900 && window.innerHeight >= 620;

export function useReel(
  reel: RefObject<HTMLElement | null>,
  pin: RefObject<HTMLElement | null>,
  monitor: RefObject<HTMLElement | null>,
  setBar: (on: boolean) => void,
) {
  const [live, setLive] = useState(canRun);
  const [folded, setFolded] = useState(false);

  useEffect(() => {
    const onResize = () => setLive(canRun());
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    const box = reel.current;
    const pinned = pin.current;
    const node = monitor.current;
    if (!box || !pinned || !node) return;
    if (!live) {
      node.style.removeProperty('transform');
      node.style.removeProperty('border-radius');
      pinned.style.removeProperty('--reel');
      return;
    }
    const onScroll = () => {
      const span = box.offsetHeight - window.innerHeight;
      const p = Math.min(1, Math.max(0, -box.getBoundingClientRect().top / span));
      const e = p * p * (3 - 2 * p);
      const w = window.innerWidth,
        h = window.innerHeight;
      const to = Math.min(w * 0.46, 880) / w; // the folded monitor's width, as a share of the screen
      const s = 1 + (to - 1) * e;
      node.style.transform = `translate(${((w - 92 - w * to) * e).toFixed(1)}px, ${(h * 0.11 * e).toFixed(1)}px) scale(${s.toFixed(4)})`;
      node.style.borderRadius = `${((14 * e) / s).toFixed(1)}px`;
      pinned.style.setProperty('--reel', e.toFixed(3));
      setFolded(e > 0.4); // the faded monitor's buttons stop taking clicks; the timeline's start
      if (e > 0) setBar(e > 0.55);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    const first = requestAnimationFrame(onScroll);
    return () => {
      cancelAnimationFrame(first);
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
    };
  }, [reel, pin, monitor, live, setBar]);

  return { live, folded };
}
