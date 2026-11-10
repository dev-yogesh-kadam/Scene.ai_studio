// A row of choices, one of them on: the theme, the motion, a view.

import type { ReactNode } from 'react';
import { classesOf } from '../cx';
import css0 from './Shared.module.css';
import css1 from './Shared2.module.css';
import css2 from './Shared3.module.css';
import css3 from './Shared4.module.css';
import css4 from '../landing/Landing2.module.css';
import css5 from '../../studio/pages/guide/GuidePage.module.css';
const css = classesOf(css0, css1, css2, css3, css4, css5);

export type Choice<T extends string | number> = { id: T; label: ReactNode; hint?: string };

export function Segmented<T extends string | number>({
  choices,
  current,
  onPick,
  className,
}: {
  choices: readonly Choice<T>[];
  current: T;
  onPick: (id: T) => void;
  className?: string;
}) {
  return (
    <div className={className ? 'seg ' + className : 'seg'}>
      {choices.map((c) => {
        const on = String(c.id) === String(current);
        return (
          <button
            key={String(c.id)}
            type="button"
            className={css(on ? 'on' : '')}
            title={c.hint || ''}
            aria-pressed={on}
            onClick={() => onPick(c.id)}
          >
            {c.label}
          </button>
        );
      })}
    </div>
  );
}
