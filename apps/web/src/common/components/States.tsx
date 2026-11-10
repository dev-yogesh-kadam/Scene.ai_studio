// What a page shows while its data loads, when there is none, and when it could not be had: one look for every page of
// the studio (U5), as the phone site's EmptyState, Skeleton and Banner. `wide`: the whole row of the grid it is in.

import type { ReactNode } from 'react';
import { classesOf, cx } from '../cx';
import css0 from './Shared2.module.css';
import s from './States.module.css';
const css = classesOf(css0);

export function EmptyState({ children, wide = false }: { children: ReactNode; wide?: boolean }) {
  return <div className={cx(css('empty'), wide && s.wide)}>{children}</div>;
}

/** Grey places for what is coming, as cells of the grid it is put in; said as "Loading" once. */
export function Skeleton({ count = 6, shape = 'tile' }: { count?: number; shape?: 'tile' | 'line' }) {
  return (
    <>
      <span className={s.said} aria-live="polite">
        Loading…
      </span>
      {Array.from({ length: count }, (_, i) => (
        <span key={i} className={cx(s.bone, s[shape])} aria-hidden="true" />
      ))}
    </>
  );
}

/** Why it could not be loaded, read out at once, with a way to try again. */
export function ErrorBanner({
  error,
  onRetry,
  wide = false,
}: {
  error: unknown;
  onRetry?: () => void;
  wide?: boolean;
}) {
  const text = error instanceof Error ? error.message : String(error || 'Something went wrong.');
  return (
    <p className={cx('error', wide && s.wide)} role="alert">
      {text}
      {onRetry && (
        <button type="button" className={cx('btn small quiet', s.again)} onClick={onRetry}>
          Try again
        </button>
      )}
    </p>
  );
}
