// The agent's routes the studio's panel calls: its state, one conversation's board, a plan's steps, the checks and
// retakes of what it made, and the plans the studio carries out (backend/scene/api/agent.py, api/plans.py).
import { api } from './client';
import { requestLines, type Line } from './stream';

export type AgentStatus = {
  online: boolean;
  model: string;
  models?: string[];
  detail?: string;
  prices?: Record<string, number>;
  by_tokens?: string[];
  efforts?: Record<string, { levels: string[]; default: string | null }>;
  hosted?: { id: string; name: string }[];
};

export const agentStatus = () => api<AgentStatus>('/api/agent/status');
/** The user's own settings of the agent, kept on the server (GET /api/agent/preferences). */
export type AgentPreferences = {
  retry_once: boolean;
  model: string | null; // null: the studio's default
  effort: Record<string, string>; // per model
  permission: 'all' | 'videos' | 'always'; // whether a plan runs without Approve
  explain: Record<string, boolean>; // per conversation
};
export const agentPreferences = () => api<AgentPreferences>('/api/agent/preferences');
export const setAgentPreferences = (json: Partial<AgentPreferences>) =>
  api<AgentPreferences>('/api/agent/preferences', { method: 'PUT', json });
export const compactDirection = (json: unknown) =>
  api<{ direction: string }>('/api/agent/compact', { method: 'POST', json });
export const compactSession = <T>(json: unknown) =>
  api<{ context: T }>('/api/agent/session/compact', { method: 'POST', json });
export const deleteBoard = (name: string, project: number) =>
  api<{ ok: true }>(`/api/boards/${name}?project=${project}`, { method: 'DELETE' });

/** One message to the agent, answered as lines of JSON (status, activity, thought, then the plan). */
export const planMessage = (json: unknown, signal: AbortSignal, onLine: (line: Line) => void) =>
  requestLines('/api/agent/plan', { signal, json }, onLine);

export const changeStep = <T>(step: unknown, change: unknown) =>
  api<T>('/api/agent/step', { method: 'POST', json: { step, change } });
export const reviewItem = <T>(json: unknown) => api<T>('/api/agent/review', { method: 'POST', json });
export const reroll = <T>(item: number) => api<{ retake: T }>('/api/agent/reroll', { method: 'POST', json: { item } });
export const storyboard = <T>(json: unknown) => api<T>('/api/agent/storyboard', { method: 'POST', json });
export const animate = <T>(json: unknown) => api<T>('/api/agent/animate', { method: 'POST', json });

export const makePlan = (json: unknown) => api<{ id: number }>('/api/agent/plans', { method: 'POST', json });
/** `auto`: the page approves it by itself, under the user's permission (which the server holds it to). */
export const startPlan = <T>(id: number, again: boolean, auto = false) =>
  api<T>(`/api/agent/plans/${id}/${again ? 'resume' : 'approve'}`, {
    method: 'POST',
    ...(auto && !again ? { json: { auto: true } } : {}),
  });
/** What resuming a stopped or failed plan makes again: each step, why it was not made, what is changed, the price. */
export type PlanRedo = {
  plan: number;
  steps: { step: number; name: string; kind: string; maker: string; reason: string; note: string }[];
  total: number;
};
export const planRedo = (id: number) => api<PlanRedo>(`/api/agent/plans/${id}/redo`);
export const stopPlan = (id: number) => api<unknown>(`/api/agent/plans/${id}/stop`, { method: 'POST' });
export const getPlan = <T>(id: number) => api<T>(`/api/agent/plans/${id}`);

export const rateItem = (id: number, rating: number) =>
  api<unknown>('/api/library/' + id, { method: 'PUT', json: { rating } });
export const skillsList = <T>() => api<{ skills: T[] }>('/api/skills').then((found) => found.skills || []);
