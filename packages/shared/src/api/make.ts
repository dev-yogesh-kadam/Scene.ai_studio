// Making things from the canvas's Quick actions: the project's always-on NeuralCore entries for a workflow's slots,
// and motion graphics (titles and overlays from templates, whole motion videos written as scenes), rendered on the
// studio's own machine (backend/scene/api/motion.py).
import { api } from './client';

/** A NeuralCore entry that goes into one of the workflow's slots (always on in the project). */
export type CastFill = { slot: string; asset: number; name: string; kind: string; item_kind: string };

export function castFor(project: number, workflow: string) {
  return api<{ fills: CastFill[] }>(`/api/cast?project=${project}&workflow=${encodeURIComponent(workflow)}`);
}

export type MotionField = {
  id: string;
  label: string;
  type?: string; // 'choice' or text
  choices?: (string | number)[];
  names?: Record<string, string>;
  unit?: string;
  max?: number;
  placeholder?: string;
  default?: string | number;
};
export type MotionTemplate = {
  id: string;
  title: string;
  description: string;
  needs?: string; // 'video': laid over a video
  fields: MotionField[];
};
export type MotionScene = { kind: string; heading: string; text: string; items: string[] };

export function motionTemplates() {
  return api<{ ready: boolean; detail: string; templates: MotionTemplate[] }>('/api/motion/templates');
}

/** What a render would cost: the server sets how long each scene is, so it works the price out. */
export function motionEstimate(body: unknown) {
  return api<{ credits: number }>('/api/motion/estimate', { method: 'POST', json: body });
}

/** The scenes of a motion video, written by the agent's model from what it is about. */
export function writeScenes(about: string, project: number | null, model: string | null) {
  return api<{ name: string; look: string; shape: string; scenes: MotionScene[] }>('/api/motion/scenes', {
    method: 'POST',
    json: { about, project_id: project, model },
  });
}

export function motionRender(body: unknown) {
  return api<{ id: string }>('/api/motion/render', { method: 'POST', json: body });
}
