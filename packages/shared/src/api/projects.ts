// Projects, their modules, and a module laid out for the phone (in place of the studio's infinite canvas).
import { request } from './client';
import type { ModuleView, ProjectDetail, ProjectRow } from '../types/api';

/** Every project and module you have or that was shared with you. */
export function listProjects() {
  return request<{ projects: ProjectRow[] }>('/api/projects');
}

export function getProject(id: number) {
  return request<ProjectDetail>(`/api/projects/${id}`);
}

export function getModule(id: number) {
  return request<ModuleView>(`/api/mobile/modules/${id}`);
}
