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
type When = Record<string, string | string[]>;
/** `when`: the choices it is offered under, one set or a list of sets any one of which will do (Best upscale: with
 *  Upscale video or Sharpen first frame on). Not offered, it is left on its default (workflows.context). */
export type Option = {
  id: string;
  label: string;
  default: string;
  choices: Choice[];
  top?: boolean;
  when?: When | When[];
};
export type Slot = {
  id: string;
  label: string;
  kind: 'image' | 'video' | 'audio';
  optional?: boolean;
  order?: number;
  when?: When;
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

/** A workflow as GET /api/workflows/{kind}/{name} describes it: one provider model and its settings. */
export type Workflow = {
  id: string;
  title: string;
  description: string;
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

/** One row of GET /api/workflows: one provider model, a workflow of its own ("video/@seedance_2_5"). */
export type WorkflowRow = {
  id: string;
  kind: string;
  title: string;
  description?: string;
  error?: string;
  replaces?: string[];
  source?: 'generation';
  provider?: boolean;
  model?: string; // the provider's id of the model
  picture_refs?: number; // how many reference pictures it takes (0: it makes pictures from words only)
};
export type Catalog = { workflows: WorkflowRow[]; kinds: string[]; default: string };

/** A reference in a slot: a file from this computer, one the studio already keeps, or a NeuralCore entry. */
export type RefValue = {
  file?: File;
  existing?: string; // the name the studio keeps it under (comfy_name)
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
 *  that is out of use stays there for when the choice is switched back, and is not sent. */
export const inUse = (slot: Slot, options: Record<string, string>) => matches(slot.when || {}, options);

/** A picker's entries: every model, each a workflow of its own. */
export const pickerEntries = (rows: WorkflowRow[], label: (w: WorkflowRow) => string = (w) => w.title) =>
  rows.map((w) => ({ value: w.id, label: label(w) }));

/** The lengths to offer: 5, 10 and 15 seconds, and the one set now. The server says when a model can't make one. */
export const lengthChoices = (current: number) =>
  [...new Set([5, 10, 15, current])].filter((d) => Number.isFinite(d) && d > 0).sort((a, b) => a - b);

const matches = (when: When, options: Record<string, string>) =>
  Object.entries(when).every(([k, v]) => ([] as string[]).concat(v).includes(options[k]));

/** Whether an option is offered with the choices made (the server's workflows.shown). */
export const offered = (option: Option, options: Record<string, string>) =>
  !option.when || ([] as When[]).concat(option.when).some((when) => matches(when, options));

/** The options to show, in their order. */
export const optionsShown = (form: Pick<JobForm, 'wf' | 'options'>) =>
  form.wf.options.filter((o) => offered(o, form.options));

const usedSlots = (form: JobForm) => new Set(form.wf.refs.filter((s) => inUse(s, form.options)).map((s) => s.id));

/** A reference the studio already keeps, as a slot holds it. */
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
  const res = byRole(form.wf, 'resolution'); // a workflow with a RESOLUTION field instead of a size (H3 All In One)
  const ctx: Record<string, unknown> = {
    ...form.options,
    resolution: form.resolution ?? (res ? Number(form.values[res.id]) : null),
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
