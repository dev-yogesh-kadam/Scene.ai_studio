// A line icon (24px grid, drawn with the text colour): 1.6px stroke with rounded ends and corners. Drawn as elements
// from data (icons.ts), never as HTML text.

import { createElement } from 'react';
import { ICONS, type IconName } from './icons';
import { classesOf } from '../../cx';
import css0 from './Icon.module.css';
import css1 from '../../../studio/features/agent/Message.module.css';
import css2 from '../../../studio/features/agent/Plan.module.css';
const css = classesOf(css0, css1, css2);

export type { IconName };

export function Icon({ name, className = '' }: { name: IconName | string; className?: string }) {
  const parts = ICONS[name as IconName] ?? [];
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className ? `icon ${className}` : 'icon'}
      aria-hidden="true"
    >
      {parts.map(([tag, attrs], i) => createElement(tag, { key: i, ...attrs }))}
    </svg>
  );
}

/** The credit mark: the studio's Clapper Gate on its own, in the colour of the text around it, so it is white on the
 *  dark canvas and black inside a light button. */
export function CreditMark({ label = '' }: { label?: string }) {
  return (
    <svg
      viewBox="0 0 48 48"
      fill="none"
      className={css('credit-token')}
      {...(label ? { role: 'img', 'aria-label': label } : { 'aria-hidden': true })}
    >
      <path d="M5.5 12.5l35-7.2" stroke="currentColor" strokeWidth="5.6" strokeLinecap="round" />
      <rect x="5.5" y="19" width="37" height="24" rx="5" stroke="currentColor" strokeWidth="5.2" />
      <rect x="17.5" y="24.5" width="13" height="13" rx="2.2" fill="currentColor" />
    </svg>
  );
}
