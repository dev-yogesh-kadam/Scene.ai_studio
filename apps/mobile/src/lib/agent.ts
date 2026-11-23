// The agent's conversations, as the studio keeps them (apps/web/src/studio/features/agent/), so a
// conversation goes on from the phone where it left off in the studio, and the other way round:
// - board "agent" of a module: the index of its tabs {tabs, open, active};
// - board "agent-<tab id>": that tab's conversation {runs, direction, folded, workflows}.
// A message goes to POST /api/agent/plan, which answers line by line (NDJSON) as it works, read as it streams. An approved
// plan is carried out by the studio itself (/api/agent/plans): the phone starts and stops it and shows its progress.
import { getPlan, makePlan, startPlan, stopPlan } from '@scene/shared/api/agent';
import { request } from '@scene/shared/api/client';
import type { JobSettings } from '@scene/shared/types/api';

export const KEPT = 60; // turns a tab keeps
const RECALLED = 40; // earlier turns sent along with a message
export const GO =
  /^\W*(approve|approved|start|go|go ahead|yes|ok|okay|proceed|generate|generate it|make it|do it|run it|confirm)\W*$/i;

export type Use = { id?: number; asset?: number; slot: string; kind?: string; name: string };

export type Step = {
  name: string;
  kind?: string;
  credits?: number;
  workflow_title?: string;
  prompt?: string;
  why?: string;
  settings?: JobSettings & Record<string, unknown>;
  uses?: Use[];
  start?: { id: number; slot: string; name?: string };
  after?: { step: number; slot: string };
  assemble?: {
    name?: string;
    steps?: number[];
    clips?: { id: number; start: number; end: number; fade?: boolean }[];
    music_step?: number;
    music?: number;
    title?: unknown;
    end?: unknown;
    look?: unknown;
    shape?: unknown;
  };
  motion?: Record<string, unknown>;
  sound?: Record<string, unknown>;
  edit?: { clips: { id: number }[] };
  skipped?: boolean;
  job?: string;
  made?: number;
  error?: string | null;
  [key: string]: unknown;
};

export type Run = {
  instruction: string;
  reply: string;
  thought?: string;
  activity?: { icon?: string; text?: string; type?: string }[];
  steps: Step[];
  total: number;
  state: 'proposed' | 'approved' | 'answered' | 'dismissed' | string;
  at: number;
  error?: boolean;
  auto?: boolean;
  question?: { text: string; options: string[]; answer?: string } | null;
  questions?: { text: string; options: string[]; default?: string }[];
  picks?: string[];
  questionsSent?: boolean;
  continues?: boolean;
  title?: string;
  plan?: number; // the plan the studio carries out once it is approved
  planState?: string; // where it stands: running, stopping, done, failed, stopped
  [key: string]: unknown;
};

export type Conversation = {
  runs: Run[];
  direction: string;
  folded: number;
  workflows: string[];
  [key: string]: unknown;
};
export type Tab = { id: string; name: string; created: number; updated: number; spent: number | null };
export type TabIndex = { tabs: Tab[]; open: string[]; active: string | null };

const newId = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 6);

const board = <T>(project: number, kind: string) =>
  request<{ data: T }>(`/api/boards/${kind}?project=${project}`).then((r) => r.data ?? ({} as T));
const keep = (project: number, kind: string, data: unknown) =>
  request<{ ok: true }>(`/api/boards/${kind}`, { method: 'PUT', body: JSON.stringify({ project, data }) });

/** A module's conversations. The single one kept before there were tabs becomes "Agent 1", as the studio does. */
export async function loadTabs(project: number): Promise<TabIndex> {
  const saved = await board<Partial<TabIndex> & { runs?: Run[] }>(project, 'agent');
  let index: TabIndex = {
    tabs: Array.isArray(saved.tabs) ? saved.tabs : [],
    open: Array.isArray(saved.open) ? saved.open : [],
    active: saved.active ?? null,
  };
  if (!index.tabs.length) {
    const first: Tab = { id: newId(), name: 'Agent 1', created: Date.now(), updated: Date.now(), spent: null };
    if (Array.isArray(saved.runs) && saved.runs.length) await keep(project, 'agent-' + first.id, { runs: saved.runs });
    index = { tabs: [first], open: [first.id], active: first.id };
    await keep(project, 'agent', index);
  }
  return index;
}

export function saveIndex(project: number, index: TabIndex) {
  return keep(project, 'agent', index).catch(() => undefined);
}

export async function newTab(project: number, index: TabIndex): Promise<{ index: TabIndex; tab: Tab }> {
  const used = new Set(index.tabs.map((t) => t.name));
  let n = index.tabs.length + 1;
  while (used.has(`Agent ${n}`)) n += 1;
  const tab: Tab = { id: newId(), name: `Agent ${n}`, created: Date.now(), updated: Date.now(), spent: null };
  const next = { tabs: [...index.tabs, tab], open: [...index.open, tab.id], active: tab.id };
  await saveIndex(project, next);
  return { index: next, tab };
}

export async function loadConversation(project: number, tab: string): Promise<Conversation> {
  const saved = await board<Partial<Conversation>>(project, 'agent-' + tab);
  const runs = Array.isArray(saved.runs) ? saved.runs : [];
  return {
    ...saved,
    runs,
    direction: typeof saved.direction === 'string' ? saved.direction : '',
    folded: Math.min(Number(saved.folded) || 0, runs.length),
    workflows: Array.isArray(saved.workflows) ? saved.workflows.filter((w) => typeof w === 'string') : [],
  };
}

const WRITER = 'm' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8); // this page's copy

/** Each save is one version newer than the copy loaded (`rev`): the studio keeps only a newer one than it has, so a
 *  phone left open on an old copy never writes over what the studio did since (a refused save leaves it as it is). */
export function saveConversation(project: number, tab: string, convo: Conversation) {
  const drop = Math.max(0, convo.runs.length - KEPT);
  convo.rev = (Number(convo.rev) || 0) + 1;
  return keep(project, 'agent-' + tab, {
    runs: convo.runs.slice(-KEPT),
    direction: convo.direction,
    folded: Math.max(0, convo.folded - drop),
    workflows: convo.workflows,
    rev: convo.rev,
    writer: WRITER,
  }).catch(() => undefined);
}

/** The earlier turns sent with a message: the newest, less those already folded into the direction. */
function recalled(convo: Conversation) {
  return convo.runs
    .slice(Math.max(convo.folded, convo.runs.length - RECALLED))
    .filter((r) => !r.error)
    .map((r) => ({
      instruction: r.instruction,
      reply: r.reply,
      steps: r.steps.map((s) => ({ name: s.name, uses: (s.uses ?? []).map((u) => u.name) })),
    }));
}

export type AgentEvent =
  | { type: 'status'; text: string }
  | { type: 'activity' | 'thought'; text?: string; icon?: string }
  | { type: string; [key: string]: unknown };

type PlanAnswer = Run & { direction?: string; balance?: number; memory_used?: unknown[] };

/** Send a message; `onEvent` gets what the agent does as it works. Gives the new turn, already added to `convo`. */
export async function ask(
  project: number,
  tab: Tab,
  convo: Conversation,
  text: string,
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<{ run: Run; balance?: number }> {
  const response = await fetch('/api/agent/plan', {
    method: 'POST',
    signal,
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', Accept: 'application/x-ndjson' },
    body: JSON.stringify({
      instruction: text,
      project_id: project || null,
      selection: [],
      model: null,
      direction: convo.direction,
      run: tab.id,
      tab: tab.name,
      workflows: convo.workflows,
      history: recalled(convo),
    }),
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail ?? `The agent couldn't answer (${response.status}).`);
  }
  let answer: PlanAnswer | null = null;
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  const handle = (line: string) => {
    if (!line.trim()) return;
    const event = JSON.parse(line) as AgentEvent & Record<string, unknown>;
    if (event.type === 'error') throw new Error(String(event.message ?? 'The agent stopped. Try again.'));
    if (event.type === 'plan') answer = event as unknown as PlanAnswer;
    else onEvent(event);
  };
  for (;;) {
    const { done, value } = await reader.read();
    if (value) buffer += decoder.decode(value, { stream: true });
    let cut = buffer.indexOf('\n');
    while (cut >= 0) {
      handle(buffer.slice(0, cut));
      buffer = buffer.slice(cut + 1);
      cut = buffer.indexOf('\n');
    }
    if (done) break;
  }
  handle(buffer);
  if (!answer) throw new Error('The agent stopped before it finished. Try again.');
  const made = answer as PlanAnswer;
  const run: Run = {
    instruction: text,
    reply: made.reply,
    thought: made.thought,
    activity: made.activity ?? [],
    seconds: made.seconds,
    chips: made.chips ?? {},
    memoryUsed: made.memory_used ?? [],
    steps: made.steps ?? [],
    total: made.total ?? 0,
    state: made.steps?.length ? 'proposed' : 'answered',
    at: Date.now(),
    ui: {},
    llm: made.llm ?? null,
    question: made.question ?? null,
    questions: made.questions ?? [],
    continues: !!made.continues,
    context: made.context ?? null,
  };
  if (made.direction) convo.direction = made.direction;
  convo.runs.push(run);
  return { run, balance: made.balance };
}

/** Where a plan the studio carries out stands (GET /api/agent/plans/{id}, or the live connection's "plans"). */
export type ServerPlan = {
  id: number;
  state: string;
  steps: { job?: string | null; waiting?: boolean; error?: string | null }[];
};

/** A plan that is being carried out, or is being stopped. */
export const running = (run: Run) => run.planState === 'running' || run.planState === 'stopping';

/** Approve a plan: the studio prices and reserves it, then queues its steps itself, so it goes on with the app closed.
 *  A plan that stopped part way goes on from where it stopped: what is left is priced and reserved again. */
export async function approvePlan(project: number, tab: string, run: Run) {
  run.state = 'approved';
  run.approvedAt = (run.approvedAt as number | undefined) ?? Date.now();
  if (!run.plan)
    run.plan = (await makePlan({ steps: run.steps, name: run.title || '', tab, project_id: project || null })).id;
  const again = run.steps.some((step) => step.job || step.made || step.error);
  const plan = await startPlan<ServerPlan>(run.plan, again);
  for (const step of run.steps) if (step.error && !step.made) step.error = null; // tried again
  applyPlan(run, plan);
  return plan;
}

/** Stop a plan: the steps not queued yet stay unqueued; what is queued runs on. */
export const stopRun = (run: Run) => (run.plan ? stopPlan(run.plan).then(() => undefined) : Promise.resolve());

/** What the studio said about a plan, on its run: the job of each step queued, a step waiting, a step refused. Gives
 *  whether anything changed. */
export function applyPlan(run: Run, plan: ServerPlan) {
  if (plan.id !== run.plan) return false;
  let changed = run.planState !== plan.state;
  plan.steps.forEach((shown, i) => {
    const step = run.steps[i];
    if (!step) return;
    if (shown.job && !step.job) {
      step.job = shown.job;
      step.queuedAt = step.queuedAt || Date.now();
      changed = true;
    }
    if (shown.error && !step.error) {
      step.error = shown.error;
      changed = true;
    }
    if (!!shown.waiting !== !!step.waiting) {
      step.waiting = shown.waiting;
      changed = true;
    }
  });
  run.planState = plan.state;
  return changed;
}

/** The plans of a conversation that were not over when it was last seen: where they stand now. */
export async function followPlans(convo: Conversation) {
  let changed = false;
  for (const run of convo.runs.filter((r) => r.plan && !['done', 'failed', 'stopped'].includes(r.planState ?? ''))) {
    const plan = await getPlan<ServerPlan>(run.plan as number).catch(() => null);
    if (plan && applyPlan(run, plan)) changed = true;
  }
  return changed;
}

/** Steps whose jobs have finished get the item they made, so the conversation can show it. Gives whether any changed. */
export function collectResults(convo: Conversation, jobs: { id: string; status: string; items: { id: number }[] }[]) {
  let changed = false;
  for (const run of convo.runs) {
    for (const step of run.steps) {
      if (step.job && !step.made) {
        const job = jobs.find((j) => j.id === step.job);
        if (job?.status === 'done' && job.items[0]) {
          step.made = job.items[0].id;
          changed = true;
        }
      }
    }
  }
  return changed;
}

/** What a plan costs: the steps not left out. */
export function recount(run: Run) {
  run.total = run.steps.reduce((sum, s) => sum + (s.skipped ? 0 : (s.credits ?? 0)), 0);
}
