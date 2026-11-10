// A made item of the library, as /api/library gives it, and the facts about it worth showing.

import { duration } from '../format';

export type Item = {
  id: number;
  name: string;
  kind: string; // image, video, audio, text
  workflow: string;
  filename: string;
  size?: number;
  created: number;
  seconds?: number | null;
  cost?: number | null;
  job_id?: string | null;
  project_id?: number | null;
  project_name?: string | null;
  summary?: string;
  rating?: number | null;
  user_name?: string;
  user_email?: string;
  settings?: {
    prompt?: string;
    values?: Record<string, unknown>;
    refs?: Record<string, { name?: string; comfy_name?: string }>;
    options?: Record<string, string>;
    details?: [string, unknown][];
    workflow_title?: string;
    [key: string]: unknown;
  };
  context?: {
    seed?: number | null;
    width?: number;
    height?: number;
    resolution?: number | string;
    orientation?: string;
    duration?: number;
    clips?: number;
    [key: string]: unknown;
  };
  [key: string]: unknown;
};

const title = (text: unknown) =>
  String(text)
    .replace(/_/g, ' ')
    .replace(/^./, (c) => c.toUpperCase());
const fileSize = (bytes = 0) =>
  bytes >= 1e9
    ? (bytes / 1e9).toFixed(1) + ' GB'
    : bytes >= 1e6
      ? (bytes / 1e6).toFixed(1) + ' MB'
      : Math.round((bytes || 0) / 1e3) + ' KB';

/** The prompt a generation was made with. Older items don't store it separately: the longest text setting then. */
export function promptOf(item: Item) {
  const settings = item.settings || {};
  if (settings.prompt != null) return settings.prompt;
  return (
    Object.values(settings.values || {})
      .filter((v): v is string => typeof v === 'string')
      .sort((a, b) => b.length - a.length)[0] || ''
  );
}

/** The seed it was made with, for "Reuse seed" (only work made with a seed has one). */
export const seedOf = (item: Item) => (item.context && item.context.seed != null ? item.context.seed : null);

/** The facts about a generation that are worth showing: [label, value] pairs, empty ones left out. */
export function detailsOf(item: Item, { owner = false } = {}): [string, string][] {
  const s = item.settings || {};
  const c = item.context || {};
  const made = new Date(item.created * 1000);
  const refs = Object.values(s.refs || {})
    .map((r) => r.name || r.comfy_name)
    .filter(Boolean);
  const rows: ([string, unknown] | false)[] = [
    owner && ['Made by', `${item.user_name} · ${item.user_email}`],
    ['Type', title(item.kind)],
    ['Workflow', s.workflow_title || title(item.workflow.split('/')[1])],
    ...Object.entries(s.options || {}).map(([k, v]): [string, string] => [title(k), title(v)]),
    [
      'Resolution',
      c.width
        ? `${c.width} × ${c.height}` + (c.resolution ? ` (${c.resolution}p ${c.orientation || ''})` : '')
        : c.resolution
          ? c.resolution + 'p'
          : null,
    ],
    [
      'Length',
      c.duration ? (c.clips && c.clips > 1 ? `${c.clips} clips of ${c.duration} s` : `${c.duration} s`) : null,
    ],
    ['Seed', c.seed != null ? String(c.seed) : null],
    ...(s.details || []).map(([k, v]): [string, string] => [
      k,
      typeof v === 'boolean' ? (v ? 'On' : 'Off') : String(v),
    ]),
    ['References', refs.join(', ')],
    ['Project', item.project_name],
    ['Date', made.toLocaleDateString([], { dateStyle: 'long' })],
    ['Time', made.toLocaleTimeString([], { timeStyle: 'short' })],
    ['Render time', item.seconds ? duration(item.seconds) : null],
    ['Credits', item.cost ? String(item.cost) : null],
    ['File', `${item.filename} · ${fileSize(item.size)}`],
    ['Generation ID', String(item.id)],
    ['Job ID', item.job_id],
  ];
  return rows.filter((row): row is [string, string] => !!row && row[1] != null && row[1] !== '') as [string, string][];
}
