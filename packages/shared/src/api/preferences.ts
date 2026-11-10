// The user's choices in the studio's pages, kept on the server so they follow the user (GET/PUT /api/preferences).
import { api } from './client';

export type StudioPreferences = {
  workflows: Record<string, string>; // the workflow used last, per kind
  kind: string | null; // the kind Create showed last
  project: number | null; // the project Create used last
  skills: string[]; // the skills used lately, newest first
  seen: string[]; // the one-time tips already shown
};

export const studioPreferences = () => api<StudioPreferences>('/api/preferences');
export const setStudioPreferences = (json: Partial<StudioPreferences>) =>
  api<StudioPreferences>('/api/preferences', { method: 'PUT', json });
