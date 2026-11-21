// A module's NeuralCore: its cast (entries by name, each with its controls), the memory the agent and its skills keep
// (notes as a tree of paths, and the record of every file of the module), and what the agent remembers of the user in
// every project (backend/scene/api/kit.py, backend/scene/api/core.py).
import { api } from './client';

/** One entry of the cast, as GET /api/kit lists it. */
export type CastEntry = {
  id: number;
  name: string;
  type: string;
  kind: string; // image, video, audio, text
  tag?: string;
  item?: number | null;
  url?: string;
  always?: boolean | number;
  named?: boolean | number;
  about?: string;
  use_note?: string;
  look_of?: number;
  variant?: string;
  from_scene?: number;
  palette?: string;
  relations?: { to: number; relation: string; blood: boolean }[];
};

export type MemoryLeaf = { path: string; value: unknown; writer?: string; updated?: number };
export type AssetRecord = {
  id: string;
  name: string;
  kind: string;
  item?: number;
  url?: string;
  made?: string;
  [key: string]: unknown;
};
export type Memory = {
  writable?: boolean;
  leaves: MemoryLeaf[];
  cast?: unknown;
  assets: { records: AssetRecord[]; total: number };
};

export function castEntries(project: number) {
  return api<{ entries: CastEntry[] }>('/api/kit?project=' + project).then((found) => found.entries);
}

export function changeEntry(id: number, json: Partial<CastEntry> & Record<string, unknown>) {
  return api<CastEntry>('/api/kit/' + id, { method: 'PUT', json });
}

export function removeEntry(id: number) {
  return api<{ ok: true }>('/api/kit/' + id, { method: 'DELETE' });
}

/** The whole cast in a new order. */
export function orderEntries(project: number | null, ids: number[]) {
  return api<{ entries: CastEntry[] }>('/api/kit/order', { method: 'POST', json: { project_id: project, ids } });
}

/** An asset sheet (a CSV a spreadsheet exports: type, name, image link and notes a row): every row's picture fetched. */
export function importSheet(file: File, project: number | null) {
  const data = new FormData();
  data.append('file', file, file.name);
  data.append('project_id', String(project || ''));
  return api<{
    added: { new?: boolean }[];
    looks: unknown[];
    failed: { row: number; name: string; reason: string }[];
    left_out: { row: number; name?: string; reason: string }[];
  }>('/api/kit/sheet', { method: 'POST', body: data });
}

export function coreMemory(project: number) {
  return api<Memory>('/api/core/memory?project=' + project);
}

export function putState(project: number, path: string, value: unknown) {
  return api<{ ok: true }>('/api/core/state', { method: 'PUT', json: { project_id: project, path, value } });
}

export function deleteState(project: number, path: string) {
  return api<{ ok: true }>(`/api/core/state?project=${project}&path=${encodeURIComponent(path)}`, { method: 'DELETE' });
}

/** What the agent remembers of the user in one module (memory is never shared between modules). */
export function remembered(project: number) {
  return api<{ entries: { key: string; value: string }[] }>(`/api/remembered?project=${project}`);
}

export function forget(project: number, key: string) {
  return api<{ ok: true }>(`/api/remembered?project=${project}&key=${encodeURIComponent(key)}`, { method: 'DELETE' });
}
