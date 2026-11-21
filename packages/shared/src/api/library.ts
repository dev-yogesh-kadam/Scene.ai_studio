// The library: a page at a time, one item, rating, renaming and deleting, and the addresses of its files.
import { apiUrl, request } from './client';
import type { ItemKind, LibraryItem, LibraryPage } from '../types/api';

export const PAGE = 30;

/** `project` with `exact`: only that module's (or project canvas's) own items. */
export type LibraryFilter = {
  kind?: ItemKind | '';
  starred?: boolean;
  q?: string;
  project?: number;
  exact?: boolean;
  limit?: number;
};

export function listLibrary(filter: LibraryFilter, offset = 0) {
  const params = new URLSearchParams({ offset: String(offset), limit: String(filter.limit ?? PAGE) });
  if (filter.project) params.set('project', String(filter.project));
  if (filter.exact) params.set('exact', '1');
  if (filter.kind) params.set('kind', filter.kind);
  if (filter.starred) params.set('starred', '1');
  if (filter.q?.trim()) params.set('q', filter.q.trim());
  return request<LibraryPage>(`/api/mobile/library?${params}`);
}

export function getItem(id: number) {
  return request<LibraryItem>(`/api/mobile/library/${id}`);
}

/** 1 = starred (best take), -1 = thumbs down, 0 = clear. */
export function rateItem(id: number, rating: 1 | 0 | -1) {
  return request<{ ok: true }>(`/api/library/${id}`, { method: 'PUT', body: JSON.stringify({ rating }) });
}

export function renameItem(id: number, name: string) {
  return request<{ ok: true }>(`/api/library/${id}`, { method: 'PUT', body: JSON.stringify({ name }) });
}

export function deleteItem(id: number) {
  return request<{ ok: true }>(`/api/library/${id}`, { method: 'DELETE' });
}

/** A text item's words (a transcript). */
export async function itemText(id: number) {
  const response = await fetch(fileUrl(id), { credentials: 'same-origin' });
  if (!response.ok) throw new Error(`Couldn't open it (${response.status})`);
  return response.text();
}

/** A file's bytes (a sound's waveform is drawn from them). */
export async function fileBytes(url: string) {
  return (await fetch(url, { credentials: 'same-origin' })).arrayBuffer();
}

/** A link anyone can open, without signing in, for a while: the full address and when it runs out. */
export async function shareLink(id: number) {
  const made = await request<{ path: string; expires: number }>(`/api/library/${id}/share`, { method: 'POST' });
  return { url: location.origin + made.path, expires: made.expires };
}

export function stopSharing(id: number) {
  return request<{ ok: true }>(`/api/library/${id}/share`, { method: 'DELETE' });
}

/** Put a file from the phone into the library (and the module's canvas, with `project`). */
export function upload(file: { uri: string; name: string; type: string }, project?: number) {
  const form = new FormData();
  form.append('file', file as unknown as Blob);
  if (project) form.append('project_id', String(project));
  return request<LibraryItem>('/api/library/upload', { method: 'POST', body: form });
}

/** Mark a library item as a reference slot of a job: the studio keeps it and sends it to the provider when the job runs. */
export function asReference(id: number, kind?: string) {
  return request<{ comfy_name: string; name: string }>(
    `/api/library/${id}/reference${kind ? `?kind=${encodeURIComponent(kind)}` : ''}`,
    { method: 'POST' },
  );
}

export const fileUrl = (id: number) => apiUrl(`/api/library/${id}/file`);
export const posterUrl = (id: number) => apiUrl(`/api/library/${id}/poster`);
