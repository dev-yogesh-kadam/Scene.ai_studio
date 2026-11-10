// Bulk generation, an admin's tool: one test (several prompts × many workflows, the same seed for all) made as one run,
// shown on the compare board. Free. backend/scene/api/bulk.py.
import { api } from './client';

/** A workflow as the board lists it: what it needs, so a test that can't feed it leaves it out. */
export type BulkWorkflow = {
  id: string;
  title: string;
  error?: string;
  needs_other: string[];
  needs_pictures: number;
  pictures: number;
};

export type RunRow = {
  run: string;
  prompt: string;
  created: number;
  cells: number;
  done: number;
  failed: number;
  queued: number;
  running: number;
};

export type Cell = {
  job: string;
  row: number;
  workflow: string;
  take: number;
  status: string;
  seconds: number | null;
  started?: number | null;
  seed?: number | null;
  error?: string;
  items: { id: number; kind: string; name: string; rating?: number }[]; // rating 1: starred, the best of its row
};

export type Grid = {
  run: string;
  prompts: string[];
  rows: number[];
  takes: number;
  same_seed: boolean;
  workflows: { id: string; title: string }[];
  cells: Cell[];
};

export function bulkWorkflows(kind: string) {
  return api<{ workflows: BulkWorkflow[] }>('/api/bulk/workflows?kind=' + kind).then((found) => found.workflows);
}

export function bulkRuns() {
  return api<{ runs: RunRow[] }>('/api/bulk/runs').then((found) => found.runs);
}

export function bulkRun(run: string) {
  return api<Grid>('/api/bulk/runs/' + run);
}

/** Start a test: kind, prompts, workflows, quality, takes, same_seed, project_id, (video) resolution, orientation,
 *  duration, and the pictures. */
export function startBulk(form: FormData) {
  return api<{ run: string; skipped: { title: string; why: string }[] }>('/api/bulk', { method: 'POST', body: form });
}

/** Cancel every render of a run still waiting; the ones running finish. */
export function stopRun(run: string) {
  return api<{ ok: true }>(`/api/bulk/runs/${run}`, { method: 'DELETE' });
}

/** Make one cell again. */
export function cellAgain(run: string, job: string) {
  return api<{ ok: true }>(`/api/bulk/runs/${run}/again`, { method: 'POST', json: { job } });
}
