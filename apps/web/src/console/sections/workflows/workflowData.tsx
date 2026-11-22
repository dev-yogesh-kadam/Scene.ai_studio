import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../shared/Console.module.css';
const css = classesOf(css0, css1);
// What the Workflows section reads (GET /api/admin/workflows), and how a workflow's state is said. Each workflow is one
// model a provider offers ("video/@seedance_2_5").

export type Workflow = {
  id: string;
  kind: string;
  title: string;
  description?: string;
  source?: string;
  provider?: boolean;
  model?: string; // the provider's id of the model
  audience: string;
  example?: number;
  jobs: number;
  done: number;
  failed: number;
  avg_seconds?: number | null;
  last_used?: number | null;
  resolutions_off?: string[];
  featured?: boolean; // first in the agent's model picker
  new?: boolean; // a NEW badge there
};
export type Report = {
  workflows: Workflow[];
  new_admins_only: boolean;
  resolutions_off?: Record<string, string[]>;
};

export const AUDIENCE = [
  { id: 'everyone', label: 'Everyone' },
  { id: 'admins', label: 'Admins only' },
  { id: 'off', label: 'Off' },
];
export const PILL: Record<string, readonly [string, string]> = {
  everyone: ['done', 'Everyone'],
  admins: ['running', 'Admins only'],
  off: ['cancelled', 'Off'],
};

export const Tag = ({ of }: { of: readonly [string, string] }) => <span className={css('pill ' + of[0])}>{of[1]}</span>;

/** A workflow with no price yet: it would be made for free. */
export const needsAttention = (w: Workflow) => !w.example;
export const succeeded = (w: Workflow) =>
  w.done + w.failed ? Math.round((100 * w.done) / (w.done + w.failed)) + '%' : '';
