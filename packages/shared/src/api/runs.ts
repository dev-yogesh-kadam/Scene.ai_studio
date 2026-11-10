// Jobs: the queue (GET /api/mobile/jobs), retry and cancel, and starting new ones from a prompt.
import { postJson, request } from './client';
import type { Estimate, JobSettings, JobsAnswer, Workflow } from '../types/api';

export function listJobs() {
  return request<JobsAnswer>('/api/mobile/jobs');
}

/** Run a failed or cancelled job again; charged like a new job. */
export function retryJob(id: string) {
  return request<{ id: string; credits: number }>(`/api/jobs/${encodeURIComponent(id)}/retry`, { method: 'POST' });
}

/** Cancel a waiting or running job (credits come back), or take a finished one off the list. */
export function removeJob(id: string) {
  return request<{ ok: true }>(`/api/jobs/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export function listWorkflows() {
  return request<{ workflows: Workflow[] }>('/api/mobile/workflows');
}

export function estimate(settings: JobSettings) {
  return postJson<Estimate>('/api/estimate', settings);
}

/** POST /api/jobs takes a multipart form with the settings as JSON (studio.create_job), and a file per reference
 *  slot filled from the phone, named "ref:<slot>". */
export function createJob(
  settings: JobSettings,
  files: Record<string, { uri: string; name: string; type: string }> = {},
) {
  const form = new FormData();
  form.append('settings', JSON.stringify(settings));
  for (const [slot, file] of Object.entries(files)) form.append(`ref:${slot}`, file as unknown as Blob);
  return request<{ id: string; credits: number; resolution_note: string }>('/api/jobs', { method: 'POST', body: form });
}
