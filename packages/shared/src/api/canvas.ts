// The studio's canvas: its saved layout (a board per project), what is on it (the library's items with their settings,
// NeuralCore entries, the named boards finished jobs placed results on), and bringing files and library items onto it.
// The item and entry shapes are the caller's (the studio's Item), so they are type parameters here.
import { api } from './client';

/** The saved layout of a project's canvas (backend/scene/api/boards.py); `data` is the page's own JSON. */
export function getBoard<T>(name: string, project: number | null) {
  return api<{ data: T | null }>(`/api/boards/${name}?project=${project ?? 0}`);
}

/** keepalive: the page may be going away (it is closed, or left), and the save must still reach the studio. */
export function putBoard(name: string, project: number | null, data: unknown, keepalive = false) {
  return api<{ ok: true }>(`/api/boards/${name}`, { method: 'PUT', keepalive, json: { project, data } });
}

/** Every item of a project, settings and all (`all=1`), the newest first; project 0: everything. */
export function canvasItems<T>(project: number) {
  return api<{ items: T[] }>('/api/library?all=1' + (project ? '&project=' + project : ''));
}

/** Results placed on named boards ("Characters", "Outputs") by the jobs that made them. */
export function placement<T>(project: number) {
  return api<{ boards: T[] }>('/api/library/placement?project=' + project);
}

/** Put a file into the library and the project; its id. */
export function uploadFile(file: File, project: number | null) {
  const data = new FormData();
  data.append('file', file, file.name);
  data.append('project_id', project ? String(project) : '');
  return api<{ id: number }>('/api/library/upload', { method: 'POST', body: data });
}

/** Move a library item into another project. */
export function moveItem(id: number, project: number | null) {
  return api<{ ok: true }>('/api/library/' + id, { method: 'PUT', json: { project_id: project } });
}
