// What the Sessions list and the watching panes share.

import { number } from '../shared/ui';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../../../common/components/Shared4.module.css';
import css3 from './parts.module.css';
import css4 from '../shared/Console.module.css';
const css = classesOf(css0, css1, css2, css3, css4);

export type SessionRow = {
  ref: string;
  state: string;
  user_name: string;
  user_email: string;
  parent_name?: string;
  project_name?: string;
  parent_ref?: string;
  project_ref?: string;
  model?: string;
  percent?: number;
  context_tokens: number;
  context_window: number;
  compacts?: number;
  messages: number;
  active: number;
};

const STATE_PILL: Record<string, string> = { answering: 'running', live: 'done', idle: 'cancelled', deleted: 'failed' };

export const tokens = (n: number) =>
  n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? Math.round(n / 1e3) + 'k' : number(n);
export const where = (s: SessionRow) =>
  s.parent_name ? `${s.parent_name} › ${s.project_name}` : s.project_name || 'All work';
export const StatePill = ({ state }: { state: string }) => (
  <span className={css('pill ' + (STATE_PILL[state] || ''))}>{state[0].toUpperCase() + state.slice(1)}</span>
);

export function Fullness({ s }: { s: SessionRow }) {
  const share = Math.min(100, s.percent || 0);
  return (
    <div className={css('ses-meter')} title={`${number(s.context_tokens)} of ${number(s.context_window)} tokens`}>
      <div className={css('bar-track')}>
        <div className={css('bar-value' + (share >= 80 ? ' high' : ''))} style={{ width: `${share}%` }} />
      </div>
      <span className="muted small">{`${share}%` + (s.compacts ? ` · compacted ${s.compacts}×` : '')}</span>
    </div>
  );
}
