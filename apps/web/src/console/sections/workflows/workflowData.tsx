import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../shared/Console.module.css';
const css = classesOf(css0, css1);
// What the Workflows section reads, and how a workflow's state is said.

export type Missing = { files: { file: string; node: string; type: string; input: string }[]; nodes: string[] };
export type Workflow = {
  id: string;
  title: string;
  kind: string;
  file: string;
  audience: string;
  error?: string;
  missing?: Missing | null;
  example?: number;
  jobs: number;
  done: number;
  failed: number;
  avg_seconds?: number | null;
  last_used?: number | null;
  changed?: number | null;
  presets?: boolean | number;
  resolutions_off?: string[];
};
export type Drop = { seen: number; new: string[]; updated: string[]; removed: string[] };
export type Report = {
  workflows: Workflow[];
  drops: Drop[];
  since?: number | null;
  new_admins_only: boolean;
  nodes_saved?: number | null;
  folder: string;
  resolutions_off?: Record<string, string[]>;
};
export type Version = { seen: number; change: string; file?: string; changes: string[] };

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
export const CHANGE: Record<string, readonly [string, string]> = {
  first: ['done', 'On record'],
  new: ['running', 'New'],
  updated: ['running', 'Updated'],
  removed: ['cancelled', 'Removed'],
};

export const Tag = ({ of }: { of: readonly [string, string] }) => <span className={css('pill ' + of[0])}>{of[1]}</span>;

/** What a workflow needs that the render server lacked, in one short phrase ('' when nothing). */
export function lacking(w: Workflow) {
  if (!w.missing) return '';
  const parts = [];
  if (w.missing.files.length)
    parts.push(`${w.missing.files.length} model file${w.missing.files.length === 1 ? '' : 's'}`);
  if (w.missing.nodes.length)
    parts.push(`${w.missing.nodes.length} node type${w.missing.nodes.length === 1 ? '' : 's'}`);
  return parts.length ? parts.join(' and ') + ' missing' : '';
}

export const needsAttention = (w: Workflow) => !!w.error || !!lacking(w) || !w.example;
export const succeeded = (w: Workflow) =>
  w.done + w.failed ? Math.round((100 * w.done) / (w.done + w.failed)) + '%' : '';
