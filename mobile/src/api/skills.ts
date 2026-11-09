// The agent's skills: read-only recipes kept on the server.
import { request } from './client';
import type { Skill } from '@/types/api';

export function listSkills() {
  return request<{ skills: Skill[] }>('/api/skills');
}
