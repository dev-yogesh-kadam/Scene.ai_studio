// A panel that slides in from the right for the details of one user or job. It rides on a spring: its head can be
// dragged and flicked to the right to put it away, it leaves the way it came, and the shade behind it follows it.

import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { Spring, project, rubberband, tracker } from '../../../common/motion/spring';
import { markBusy } from '../../../common/busy';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared3.module.css';
import css1 from './Drawer.module.css';
const css = classesOf(css0, css1);

type Close = (velocity?: number) => void;

export function Drawer({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: (close: Close) => ReactNode;
}) {
  const backdrop = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLElement>(null);
  const spring = useRef<Spring | null>(null);
  const closing = useRef(false);
  const left = useRef(onClose);
  useLayoutEffect(() => {
    left.current = onClose;
  });
  const width = () => panel.current?.offsetWidth || 580;
  const [close] = useState<Close>(() => (velocity?: number) => {
    if (closing.current) return;
    closing.current = true;
    if (backdrop.current) backdrop.current.style.pointerEvents = 'none';
    spring.current?.to(panel.current?.offsetWidth || 580, {
      response: 0.3,
      velocity: typeof velocity === 'number' ? velocity : undefined,
      done: () => left.current(),
    });
  });
  useLayoutEffect(() => {
    const motion = new Spring(width(), (x) => {
      if (panel.current) panel.current.style.transform = x ? `translateX(${x}px)` : '';
      backdrop.current?.style.setProperty('--shown', String(Math.max(0, Math.min(1, 1 - x / width()))));
    });
    spring.current = motion;
    motion.to(0, { response: 0.35 });
    const done = markBusy();
    return () => {
      motion.stop();
      done();
    };
  }, []);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    };
    document.addEventListener('keydown', key);
    return () => document.removeEventListener('keydown', key);
  }, [close]);

  // The head is the handle. Past the left edge it gives a little; let go far enough or fast enough and it goes away.
  const grab = (e: ReactPointerEvent<HTMLDivElement>) => {
    const motion = spring.current;
    if (
      e.button !== 0 ||
      (e.target as Element).closest('button, a, input, select, textarea') ||
      closing.current ||
      !motion
    )
      return;
    const head = e.currentTarget;
    head.setPointerCapture(e.pointerId);
    motion.stop();
    const from = { pointer: e.clientX, x: motion.x };
    const speed = tracker();
    speed.add(e.clientX);
    const onMove = (ev: PointerEvent) => {
      speed.add(ev.clientX);
      const x = from.x + ev.clientX - from.pointer;
      motion.set(x < 0 ? -rubberband(-x, width()) : x);
    };
    const end = () => {
      head.removeEventListener('pointermove', onMove);
      head.removeEventListener('pointerup', end);
      head.removeEventListener('pointercancel', end);
      const velocity = speed.velocity().x;
      if (motion.x + project(velocity) > width() / 3) close(velocity);
      else motion.to(0, { response: 0.3, damping: Math.abs(velocity) > 400 ? 0.8 : 1, velocity });
    };
    head.addEventListener('pointermove', onMove);
    head.addEventListener('pointerup', end);
    head.addEventListener('pointercancel', end);
  };
  return createPortal(
    <div
      ref={backdrop}
      className={css('drawer-backdrop')}
      onClick={(e) => {
        if (e.target === backdrop.current) close();
      }}
    >
      <aside ref={panel} className={css('drawer')} role="dialog" aria-label={title}>
        <div className={css('drawer-head')} onPointerDown={grab}>
          <h2>{title}</h2>
          <button className="btn small" onClick={() => close()}>
            Close
          </button>
        </div>
        <div className={css('drawer-body')}>{children(close)}</div>
      </aside>
    </div>,
    document.body,
  );
}
