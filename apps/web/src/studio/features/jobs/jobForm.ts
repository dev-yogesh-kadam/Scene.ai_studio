// One rule for turning a form into a job (S1, on the client): Create, the composer on Home and the canvas, and Quick
// actions all describe a job with a JobForm and send it through these functions, so a new workflow field, reference
// slot or pricing input is added in one place. The server still checks and prices what it is sent (studio.create_job).

import { api } from '../../../common/api';

export type Choice = { id: string | number; label: string; hint?: string };
export type Control = {
  id: string;
  label: string;
  role?: string | null;
  type?: string;
  default?: unknown;
  choices?: (string | number)[];
  primary?: boolean;
};
export type Option = { id: string; label: string; default: string; choices: Choice[]; top?: boolean };
export type Slot = {
  id: string;
  label: string;
  kind: 'image' | 'video' | 'audio';
  optional?: boolean;
  order?: number;
  when?: Record<string, string | string[]>;
  default?: string;
  tag?: string;
  required?: boolean;
  node?: string;
};

/** How a model's prompt names its references ("image 1", <ref_image_0>): unique when each has a name of its own. */
export type RefNaming = { unique?: boolean; tokens?: string[]; hint?: string; license?: string };
export type Warning = {
  message: string;
  when: Record<string, unknown>;
  alt?: { label: string; set: Record<string, unknown> };
};

/** A workflow as GET /api/workflows/{kind}/{name} describes it (comfy/workflows.describe). */
export type Workflow = {
  id: string;
  title: string;
  description: string;
  approximate?: boolean;
  controls: Control[];
  options: Option[];
  refs: Slot[];
  slots: Record<string, string>;
  size?: { resolution: number; orientation: string } | null;
  resolutions: number[];
  chain?: boolean;
  seeded?: boolean;
  confirm: Warning[];
  hints: string[];
  replaces?: string[];
  ref_naming?: RefNaming | null;
};

/** One row of GET /api/workflows. */
export type WorkflowRow = { id: string; kind: string; title: string; error?: string; replaces?: string[] };
export type Catalog = { workflows: WorkflowRow[]; kinds: string[]; default: string };

/** A reference in a slot: a file from this computer, one already on the render server, or a NeuralCore entry. */
export type RefValue = {
  file?: File;
  existing?: string; // its name on the render server
  assetId?: number;
  name: string;
  url?: string;
  kind?: string;
};

export type JobForm = {
  wf: Workflow;
  values: Record<string, unknown>;
  options: Record<string, string>;
  resolution: number | null;
  orientation: string | null;
  seed: string; // empty = a new random one on every Generate
  name: string;
  clips: number; // more than 1 = a long video made of chained clips
  projectId: number | null;
  parent: number | null; // the library item this is made from, so the result joins its row on the canvas
  refs: Record<string, RefValue>;
  keep?: { as: string; name: string };
};

export type Quote = {
  credits: number;
  balance: number;
  text: string;
  minutes?: number;
  choices?: Record<string, Record<string, number>>;
};

export const byRole = (wf: Workflow, role: string) => wf.controls.find((c) => c.role === role);

/** A new form for `wf`, with its defaults; `keep` carries over what was typed into the prompt. */
export function newForm(
  wf: Workflow,
  keep: Partial<Pick<JobForm, 'projectId' | 'parent'>> & { prompt?: string } = {},
): JobForm {
  const form: JobForm = {
    wf,
    values: Object.fromEntries(wf.controls.map((c) => [c.id, c.default])),
    options: Object.fromEntries(wf.options.map((o) => [o.id, o.default])),
    resolution: wf.size ? wf.size.resolution : null,
    orientation: wf.size ? wf.size.orientation : null,
    seed: '',
    name: wf.id.split('/')[1],
    clips: 1,
    projectId: keep.projectId ?? null,
    parent: keep.parent ?? null,
    refs: {},
  };
  const prompt = byRole(wf, 'prompt');
  if (prompt && keep.prompt !== undefined) form.values[prompt.id] = keep.prompt;
  return form;
}

/** Whether the workflow reads this box with the choices made: some belong to one mode only. A file left in a box
 *  that is out of use stays there for when the mode is switched back, and is not sent. */
export const inUse = (slot: Slot, options: Record<string, string>) =>
  Object.entries(slot.when || {}).every(([k, v]) => ([] as string[]).concat(v).includes(options[k]));

const usedSlots = (form: JobForm) => new Set(form.wf.refs.filter((s) => inUse(s, form.options)).map((s) => s.id));

/** A reference already on the render server, as a slot holds it. */
export const existingRef = (ref: { comfy_name: string; name: string }): RefValue => ({
  existing: ref.comfy_name,
  name: ref.name,
  url: '/api/ref-preview?name=' + encodeURIComponent(ref.comfy_name),
});

/** The job's settings, as POST /api/jobs and POST /api/estimate take them. */
export function jobSettings(form: JobForm) {
  const used = usedSlots(form);
  const refs: Record<string, { comfy_name?: string; name?: string; asset_id?: number }> = {};
  for (const [id, r] of Object.entries(form.refs)) {
    if (!used.has(id)) continue;
    if (r.existing) refs[id] = { comfy_name: r.existing, name: r.name };
    else if (r.assetId) refs[id] = { asset_id: r.assetId };
  }
  const seed = String(form.seed).trim();
  return {
    workflow: form.wf.id,
    name: form.name,
    values: form.values,
    options: form.options,
    resolution: form.resolution,
    orientation: form.orientation,
    seed_mode: seed ? 'fixed' : 'random',
    seed: seed ? Number(seed) : null,
    clips: form.wf.chain ? form.clips : 1,
    project_id: form.projectId,
    parent: form.parent,
    refs,
    keep: form.keep,
  };
}

/** What it would cost and take, and the balance. */
export const estimate = (form: JobForm) => api<Quote>('/api/estimate', { method: 'POST', json: jobSettings(form) });

/** The warnings of the workflow that apply to these settings ("a 15 s clip at 1080p takes an hour"). */
export function warningsOf(form: JobForm) {
  const dur = byRole(form.wf, 'duration');
  const ctx: Record<string, unknown> = {
    ...form.options,
    resolution: form.resolution,
    orientation: form.orientation,
    clips: form.wf.chain ? form.clips : 1,
    duration: dur ? Number(form.values[dur.id]) : undefined,
  };
  return form.wf.confirm.filter((c) =>
    Object.entries(c.when).every(([k, v]) => ([] as unknown[]).concat(v).some((x) => x === ctx[k])),
  );
}

/** Queue the job: its settings and a file for each filled slot in use, as multipart (studio.create_job). */
export function submitJob(form: JobForm) {
  const data = new FormData();
  data.append('settings', JSON.stringify(jobSettings(form)));
  const used = usedSlots(form);
  for (const [id, r] of Object.entries(form.refs)) if (r.file && used.has(id)) data.append('ref:' + id, r.file, r.name);
  return api<{ id: string; credits: number; resolution_note?: string }>('/api/jobs', { method: 'POST', body: data });
}

export const loadCatalog = () => api<Catalog>('/api/workflows');
export const loadWorkflow = (id: string) => api<Workflow>('/api/workflows/' + id);
