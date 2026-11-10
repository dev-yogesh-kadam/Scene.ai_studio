// What a job being made shows: a strip of film whose frames fill in as it goes (the reel), and, under its clock, a
// paper plane or a clapperboard looping on their own (they say nothing about how far it is), and the soft sheen that
// drifts over a running frame.

import { useEffect, useRef } from 'react';
import s from './Film.module.css';

import { cx } from '../../cx';

/** share: 0 to 1, how far the job is. */
export function Reel({ share, count = 24, className }: { share: number; count?: number; className?: string }) {
  const lit = Math.max(0, Math.min(count, Math.floor((share || 0) * count)));
  return (
    <div
      className={cx(s.reel, className)}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round((share || 0) * 100)}
    >
      {Array.from({ length: count }, (_, i) => (
        <i key={i} className={i < lit ? s.lit : i === lit ? s.next : undefined} />
      ))}
    </div>
  );
}

/** The light over a frame while it is being made. */
export function Run({ className }: { className?: string }) {
  return <span className={cx(s.run, className)} aria-hidden="true" />;
}

// A paper plane flying a route over and over: up from the bottom left, a loop-the-loop, then a glide up and away to
// the right, a short tail of smoke behind it.
const ROUTE =
  'M8 116 C55 116 98 100 128 76 C150 58 156 32 146 18 C136 4 116 8 116 27 C116 46 150 60 190 72 C228 82 262 78 292 54';
const TAIL = 55; // how much of the route the smoke covers behind the plane
const FLIGHT = 6000; // ms for one flight

export function Flight({ className }: { className?: string }) {
  const trail = useRef<SVGPathElement>(null);
  const plane = useRef<SVGGElement>(null);
  useEffect(() => {
    const offset = Math.random() * FLIGHT; // frames side by side are not in step
    let frame = requestAnimationFrame(function tick(now) {
      const path = trail.current;
      const body = plane.current;
      const len = path?.getTotalLength() ?? 0;
      if (path && body && len) {
        const t = ((now + offset) % FLIGHT) / FLIGHT;
        const at = Math.max(0.5, (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2) * (len + TAIL)); // eased
        const a = path.getPointAtLength(Math.min(at, len));
        const b = path.getPointAtLength(Math.max(0, Math.min(at, len) - 1.5));
        body.setAttribute(
          'transform',
          `translate(${a.x} ${a.y}) rotate(${(Math.atan2(a.y - b.y, a.x - b.x) * 180) / Math.PI})`,
        );
        body.style.opacity = at > len ? '0' : '1'; // gone off the end, until the next flight
        path.style.strokeDasharray = `${Math.min(TAIL, at)} ${len * 2}`;
        path.style.strokeDashoffset = String(-Math.max(0, at - TAIL));
      }
      frame = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(frame);
  }, []);
  return (
    <svg viewBox="0 0 300 125" className={cx(s.flight, className)} aria-hidden="true">
      <path ref={trail} d={ROUTE} className={s['flight-trail']} />
      <g ref={plane} className={s['flight-plane']}>
        <g className={s['flight-bob']}>
          <path d="M-11 -7 L13 0 L-11 7 L-6 0 Z M-6 0 L13 0" />
        </g>
      </g>
    </svg>
  );
}

export function Clapper({ className }: { className?: string }) {
  return (
    <div className={cx(s.clapper, className)} aria-hidden="true">
      <svg viewBox="0 0 60 50">
        <g className={s['clapper-arm']}>
          <path d="M6 22 L52 12 L54 19 L8 29 Z" />
          <path d="M16 20 L22 27 M28 17 L34 24 M40 15 L46 22" />
        </g>
        <rect x="6" y="28" width="48" height="20" rx="2" />
      </svg>
    </div>
  );
}
