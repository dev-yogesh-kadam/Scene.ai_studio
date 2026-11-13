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
  /** "generation": the generation server's (its Model option picks one of `models`); "comfy": a ComfyUI workflow. */
  source?: 'comfy' | 'generation';
  models?: ModelInfo[];
};

/** One model of the generation server (backend generation_models.catalog): from its presets file, and from the
 *  server's own list when it answered (seconds, references, frames, prices). */
export type ModelInfo = {
  model: string;
  name: string;
  about: string;
  resolutions: string[];
  shapes: string[];
  sound: string;
  frames: ('first' | 'last')[];
  seconds?: { min?: number; max?: number };
  references?: number;
  best_for?: string;
};

/** One row of GET /api/workflows. A generation workflow lists its models: each is offered on its own. */
export type WorkflowRow = {
  id: string;
  kind: string;
  title: string;
  description?: string;
  error?: string;
  replaces?: string[];
  source?: 'comfy' | 'generation';
  models?: { id: string; label: string }[];
};
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

/** Whether the workflow reads this box with the choices made: some belong to one mode only, and a generation model
 *  takes only its own frames and as many references as it says (`wf` given). A file left in a box that is out of use
 *  stays there for when the choice is switched back, and is not sent. */
export const inUse = (slot: Slot, options: Record<string, string>, wf?: Workflow | null) => {
  if (!matches(slot.when || {}, options)) return false;
  const model = wf ? chosenModel(wf, options) : undefined;
  if (!model || !wf) return true;
  if (slot.order && model.references != null && slot.order > model.references) return false;
  if (slot.id === wf.slots?.first_frame) return model.frames.includes('first');
  if (slot.id === wf.slots?.last_frame) return model.frames.includes('last');
  return true;
};

// ---------------------------------------------------------------- the generation server's models

/** The model chosen in a generation workflow's options, or undefined. */
export const chosenModel = (wf: Workflow, options: Record<string, string>) =>
  wf.source === 'generation' ? wf.models?.find((m) => m.model === options.model) : undefined;

/** A model's place in a picker: "<workflow id>#<model>". A ComfyUI workflow is its id alone. */
export const pickValue = (wf: Pick<Workflow, 'id' | 'source'>, options: Record<string, string>) =>
  wf.source === 'generation' && options.model ? `${wf.id}#${options.model}` : wf.id;

/** [workflow id, model or null] of a picker's value. */
export const splitPick = (value: string): [string, string | null] => {
  const at = value.indexOf('#');
  return at < 0 ? [value, null] : [value.slice(0, at), value.slice(at + 1)];
};

/** A picker's two groups, never mixed: ComfyUI's workflows, and the generation server's models one by one. */
export function pickerGroups(rows: WorkflowRow[], label: (w: WorkflowRow) => string = (w) => w.title) {
  const comfy = rows.filter((w) => w.source !== 'generation').map((w) => ({ value: w.id, label: label(w) }));
  const models = rows
    .filter((w) => w.source === 'generation')
    // a workflow with a Model setting is offered model by model; one without (speech, music, lip sync …) is one model
    .flatMap((w) =>
      w.models?.length
        ? w.models.map((m) => ({ value: `${w.id}#${m.id}`, label: m.label }))
        : [{ value: w.id, label: label(w) }],
    );
  return [
    { label: 'Workflows (ComfyUI)', entries: comfy },
    { label: 'Models (generation server)', entries: models },
  ].filter((g) => g.entries.length);
}

/** The lengths to offer: a generation model's own range when it is known, else 5, 10 and 15 seconds. */
export function lengthChoices(wf: Workflow, options: Record<string, string>, current: number) {
  const span = chosenModel(wf, options)?.seconds;
  const low = span?.min ?? 1;
  const high = span?.max ?? Infinity;
  const steps = span ? [low, 5, 10, 15, 20, 25, 30, high] : [5, 10, 15];
  return [...new Set([...steps, current])]
    .filter((d) => Number.isFinite(d) && d >= low && d <= high)
    .sort((a, b) => a - b);
}

/** The options and values with another model chosen: its length kept within the model's range. */
export function withModel(
  wf: Workflow,
  options: Record<string, string>,
  values: Record<string, unknown>,
  model: string,
): { options: Record<string, string>; values: Record<string, unknown> } {
  const next = { ...options, model };
  const dur = byRole(wf, 'duration');
  const span = chosenModel(wf, next)?.seconds;
  if (!dur || !span) return { options: next, values };
  const now = Number(values[dur.id] ?? dur.default ?? 5);
  const kept = Math.min(span.max ?? now, Math.max(span.min ?? now, now));
  return { options: next, values: { ...values, [dur.id]: kept } };
}

const matches = (when: When, options: Record<string, string>) =>
  Object.entries(when).every(([k, v]) => ([] as string[]).concat(v).includes(options[k]));

/** Whether an option is offered with the choices made (comfy/workflows.shown). */
export const offered = (option: Option, options: Record<string, string>) =>
  !option.when || ([] as When[]).concat(option.when).some((when) => matches(when, options));

/** The options to show, in their order. */
export const optionsShown = (form: Pick<JobForm, 'wf' | 'options'>) =>
  form.wf.options.filter((o) => offered(o, form.options));

const usedSlots = (form: JobForm) =>
  new Set(form.wf.refs.filter((s) => inUse(s, form.options, form.wf)).map((s) => s.id));

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

/** The generation server's models with what each takes ({workflow id: [model]}); the server's own list when it answers. */
export const loadModelCatalog = () => api<{ models: Record<string, ModelInfo[]> }>('/api/generation/models');
