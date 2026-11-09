// The studio as a whole: is the render server up, any message from the admins, your credits, and plans waiting for you.
import { postJson, request } from './client';
import type { Announcement, Credits, KitEntry, Status, WaitingPlan } from '@/types/api';

export function status() {
  return request<Status>('/api/status');
}

export function announcement() {
  return request<Announcement>('/api/announcement');
}

export function credits() {
  return request<Credits>('/api/mobile/credits');
}

/** Ask the admins for credits: logged for them, and pushed to their phones. */
export function requestCredits(amount: number, note: string) {
  return postJson<{ ok: true; pushed: number }>('/api/mobile/credit-request', { amount, note });
}

/** The agent's plans that wait for your approval, in any module. */
export function waitingPlans() {
  return request<{ plans: WaitingPlan[] }>('/api/mobile/waiting');
}

/** A module's NeuralCore: its cast, places, props and styles the agent keeps the same. */
export function kit(project: number) {
  return request<{ entries: KitEntry[] }>(`/api/kit?project=${project}`);
}
