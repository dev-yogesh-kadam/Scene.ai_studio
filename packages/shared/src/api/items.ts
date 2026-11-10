// The studio's library, settings and all (GET /api/library with a limit): a page at a time, newest first, what one job
// made, and one item on its own. The item shape is the caller's (the studio's Item), so it is a type parameter.
import { api } from './client';

/** `project`: a project id, "none" for items in no project, or nothing for everything; `modules`: with its modules. */
export type ItemsFilter = { kind?: string; q?: string; project?: number | 'none'; modules?: boolean; limit: number };
export type ItemsPage<T> = { items: T[]; next_cursor: string | null };

export function itemsQuery(filter: ItemsFilter, cursor = '') {
  const params = new URLSearchParams({ limit: String(filter.limit) });
  if (filter.kind) params.set('kind', filter.kind);
  if (filter.q?.trim()) params.set('q', filter.q.trim());
  if (filter.project) params.set('project', String(filter.project));
  if (filter.modules) params.set('modules', '1');
  if (cursor) params.set('cursor', cursor);
  return '/api/library?' + params.toString();
}

/** One page of the library; `cursor` is the page before's `next_cursor`. */
export function itemsPage<T>(filter: ItemsFilter, cursor = '') {
  return api<ItemsPage<T>>(itemsQuery(filter, cursor));
}

/** One item, as the list gives it. */
export function oneItem<T>(id: number) {
  return api<T>(`/api/library/${id}`);
}

/** What a job made (a picture job makes one item; a long one may make several), in its project when it has one. */
export function madeBy<T>(job: string, project?: number) {
  const params = new URLSearchParams({ job, limit: '20' });
  if (project) params.set('project', String(project));
  return api<ItemsPage<T>>('/api/library?' + params.toString()).then((page) => page.items);
}
