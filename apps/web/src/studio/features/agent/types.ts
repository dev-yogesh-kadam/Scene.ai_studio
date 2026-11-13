// What a conversation with the agent is made of, as it is kept on its board (agent-<tab>): turns ("runs"), each with
// the message, what the agent did, its reply and its plan's steps. The shape is the one the classic studio saved, so
// old conversations still open, here and on the phone site; fields a newer page does not know stay on the objects.

import type { CanvasJob } from '../../pages/canvas/arrange';

export type Review = {
  passed: boolean;
  problem?: string;
  fix?: { prompt?: string };
  checks?: { level: string }[];
};

/** One go at a shot: the step itself is the first take, retakes have this shape too. */
export type Take = {
  job?: string | null;
  made?: number | null;
  madeInfo?: { duration?: number | null; width?: number | null; height?: number | null };
  madeAll?: { id: number; kind: string; name: string }[];
  queuedAt?: number | null;
  prompt?: string;
  credits?: number;
  rating?: number;
  review?: Review;
  reviewing?: boolean;
  reviewError?: string;
  toWeigh?: boolean;
  mayRetake?: boolean;
  tries?: number;
  misses?: number;
  error?: string | null;
};

export type Retake = {
  prompt: string;
  credits: number;
  why?: string;
  settings: { refs?: Record<string, unknown> } & Record<string, unknown>;
  start?: { id: number; slot: string };
};

export type Use = { id?: number; asset?: number; name: string; kind?: string; label: string; cast?: boolean };

export type StepMenu = {
  workflows: { id: string; title: string; kind: string }[];
  shapes?: boolean;
  resolutions: number[];
  durations: number[];
};

export type Step = Take & {
  name: string;
  kind?: string;
  prompt?: string;
  facts?: string;
  workflow_title?: string;
  settings?: { workflow?: string; clips?: number; options?: Record<string, string> } & Record<string, unknown>;
  current?: { orientation?: string; resolution?: number | string; duration?: number };
  menu?: StepMenu;
  uses?: Use[];
  start?: { id: number; name: string };
  after?: { step: number } | null;
  follows?: number | null;
  camera?: { shot_size?: string; angle?: string; move?: string };
  shape?: [number, number];
  shot_number?: number;
  variation?: { n: number; of: number };
  board?: string;
  keep?: { tag: string; name: string };
  phonetic?: { word: string; say: string }[];
  why?: string;
  stage?: string;
  shot_id?: string;
  proposal?: unknown;
  assemble?: unknown;
  motion?: unknown;
  sound?: unknown;
  skipped?: boolean;
  open?: boolean;
  editing?: boolean;
  updating?: boolean;
  waiting?: boolean;
  rendering?: boolean;
  out?: boolean;
  kept?: boolean;
  chosen?: number | null;
  take2?: Take | null;
  earlier?: Take[];
  retake?: Retake | null;
  rolling?: Retake | null;
  rollBusy?: boolean;
  rollError?: string | null;
  info?: FoldState;
};

export type FoldState = { open?: boolean };
export type Part = { text?: string; id?: number; name?: string; kind?: string };
export type Chip = { name: string; kind: string; link?: string };
export type Chips = Record<string, Chip>;
export type Activity = { type: string; icon?: string; text?: string; seconds?: number; at?: number };
export type Question = {
  text: string;
  options: string[];
  details?: string[];
  default?: string;
  answer?: string;
  skipped?: boolean;
};
export type Typed = {
  text: string;
  shown: string;
  ids: number[];
  parts: Part[];
  auto?: boolean;
  from?: Run;
};
export type RunUi = {
  folded?: boolean;
  note?: string;
  more?: boolean;
  saidMore?: boolean;
  work?: FoldState;
  workItems?: Record<number, FoldState>;
  after?: FoldState;
  cancelled?: FoldState;
  ask?: { at: number; picks: (string | null)[]; other: string[] };
  retakes?: { off: number[]; note: string };
  redoClosed?: boolean; // the card offering the steps not made again was put away (Not now)
};

export type RunContext = {
  percent?: number;
  offer?: boolean;
  compacted?: boolean;
  compacting?: boolean;
  error?: string;
};

export type Run = {
  instruction: string;
  parts?: Part[];
  auto?: boolean;
  reply: string;
  thought?: string;
  activity?: Activity[];
  seconds?: number;
  chips?: Chips;
  memoryUsed?: string[];
  contentNote?: string; // the content check's one line on this plan (a warning, never a block)
  steps: Step[];
  total: number;
  state: string; // proposed, approved, answered, dismissed
  at: number;
  approvedAt?: number;
  ui: RunUi;
  llm?: { credits?: number } | null;
  error?: boolean;
  question?: Question | null;
  questions?: Question[];
  picks?: string[];
  questionsSent?: boolean;
  questionsSkipped?: boolean;
  queuedAnswer?: Typed;
  continues?: boolean;
  continued?: boolean;
  context?: RunContext | null;
  work?: { icon: string; text: string; at: number }[];
  revised?: string | null;
  rest?: Step[];
  animated?: boolean;
  plan?: number;
  planState?: string;
  title?: string;
  seenPlan?: unknown;
};

export type Pending = {
  instruction: string;
  parts: Part[];
  auto: boolean;
  stop: () => void;
  events: Activity[];
  status: string;
  started: number;
};

/** A plan the studio carries out, as the live connection and the plan routes say (backend/scene/plans.py). */
export type ServerPlan = {
  id: number;
  state: string;
  steps: { job?: string | null; waiting?: boolean; error?: string | null }[];
};

export type Spent = { video: number; image: number; audio: number; llm: number; total: number };
export type Job = CanvasJob;

export type Models = {
  list: string[];
  current: string | null;
  prices: Record<string, number>;
  byTokens: string[];
  efforts: Record<string, { levels: string[]; default: string | null }>;
  shown: (name: string) => string;
};
