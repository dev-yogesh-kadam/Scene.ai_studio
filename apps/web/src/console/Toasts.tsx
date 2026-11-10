// Short notices at the bottom right: an alert that opened or closed while the console is open. Each goes by itself, or
// is swiped away to the right; it rides a spring, so a swipe let go too soon slides back.

import { useCallback, useEffect, useLayoutEffect, useRef, type PointerEvent as ReactPointerEvent } from 'react';
import { createPortal } from 'react-dom';
import { Spring, project, tracker } from '../common/motion/spring';
import { classesOf } from '../common/cx';
import css0 from './Toasts.module.css';
import css1 from './sections/jobs/JobDrawer.module.css';
const css = classesOf(css0, css1);

export type ToastNote = { id: number; level: string; text: string };
const LEVELS: Record<string, string> = {
  critical: 'Critical',
  serious: 'Serious',
  warning: 'Warning',
  resolved: 'Resolved',
};

function Toast({ note, onOpen, onGone }: { note: ToastNote; onOpen: () => void; onGone: () => void }) {
  const node = useRef<HTMLDivElement>(null);
  const spring = useRef<Spring | null>(null);
  const swiped = useRef(false); // a swipe ends with a click on the body: it does not open the alert
  const gone = useRef(onGone);
  useLayoutEffect(() => {
    gone.current = onGone;
  });
  const width = () => node.current?.offsetWidth || 380;
  const away = useCallback(
    (velocity = 0) =>
      spring.current?.to((node.current?.offsetWidth || 380) + 24, {
        response: 0.3,
        velocity,
        done: () => gone.current(),
      }),
    [],
  );
  useLayoutEffect(() => {
    const x = new Spring(0, (v) => {
      if (!node.current) return;
      node.current.style.transform = v ? `translateX(${v}px)` : '';
      node.current.style.opacity = v > 0 ? String(Math.max(0, 1 - v / width())) : '';
    });
    spring.current = x;
    return () => x.stop();
  }, []);
  useEffect(() => {
    const timer = setTimeout(() => away(), note.level === 'critical' ? 20000 : 9000);
    return () => clearTimeout(timer);
  }, [note.level, away]);

  const grab = (e: ReactPointerEvent<HTMLDivElement>) => {
    const x = spring.current;
    if (e.button !== 0 || !x) return;
    const target = e.currentTarget;
    const pointer = e.pointerId;
    x.stop();
    const from = { pointer: e.clientX, x: x.x };
    const speed = tracker();
    swiped.current = false;
    const onMove = (ev: PointerEvent) => {
      const dx = ev.clientX - from.pointer;
      if (!swiped.current && Math.abs(dx) < 6) return;
      if (!swiped.current) {
        swiped.current = true;
        target.setPointerCapture(pointer);
      }
      speed.add(ev.clientX);
      x.set(Math.max(0, from.x + dx) - Math.max(0, -(from.x + dx)) * 0.15); // it barely moves to the left
    };
    const end = () => {
      target.removeEventListener('pointermove', onMove);
      target.removeEventListener('pointerup', end);
      target.removeEventListener('pointercancel', end);
      if (!swiped.current) return;
      setTimeout(() => {
        swiped.current = false;
      });
      const velocity = speed.velocity().x;
      if (x.x + project(velocity) > width() / 2) away(velocity);
      else x.to(0, { response: 0.3, velocity });
    };
    target.addEventListener('pointermove', onMove);
    target.addEventListener('pointerup', end);
    target.addEventListener('pointercancel', end);
  };

  return (
    <div ref={node} className={css('toast ' + note.level)} onPointerDown={grab}>
      <button
        className={css('toast-body')}
        onClick={() => {
          if (swiped.current) return;
          onGone();
          onOpen();
        }}
      >
        <b>{LEVELS[note.level] || note.level}</b>
        <span>{note.text}</span>
      </button>
      <button className="icon-btn" aria-label="Close" onClick={() => away()}>
        ×
      </button>
    </div>
  );
}

export function Toasts({
  notes,
  onOpen,
  onGone,
}: {
  notes: ToastNote[];
  onOpen: () => void;
  onGone: (id: number) => void;
}) {
  if (!notes.length) return null;
  return createPortal(
    <div className={css('toasts')} role="status" aria-live="polite">
      {notes.map((note) => (
        <Toast key={note.id} note={note} onOpen={onOpen} onGone={() => onGone(note.id)} />
      ))}
    </div>,
    document.body,
  );
}
