// Shapes of the backend's JSON. Each type names the route and the code it was read from.

/** The user as /api/auth/mobile/login gives it (backend/scene/api/auth.py, mobile_login). */
export type User = {
  id: number;
  email: string;
  name: string;
  role: string;
  credits: number;
};

/** GET /api/auth/me: user_for_token in backend/scene/api/deps.py, plus `console` for staff (auth.shown). */
export type Me = User & {
  created: number;
  mfa_enabled: number; // 0 or 1
  /** Set when an admin is looking at the studio as this user: read only. */
  viewing?: { by: string };
  console?: { url: string; port: number };
};

/** GET /api/auth/state (backend/scene/api/auth.py, auth_state): what the sign-in page needs before anyone is signed in.
 *  `invite_required`: new accounts are open but ask for the studio's invite code (sent as `invite` to register). */
export type AuthInfo = { first_run: boolean; signup_open: boolean; invite_required?: boolean };

/** POST /api/auth/mobile/login, when the password (and code, if asked) is right. */
export type MobileLogin = {
  token: string;
  expires_in: number; // seconds
  user: User;
};

/** The 401 answer of a sign-in that needs the 6-digit code (auth.check_sign_in). */
export type MfaRequired = {
  detail: string;
  mfa_required: true;
};

/** What a workflow makes. */
export type Kind = 'video' | 'image' | 'audio';
/** What a library item is: also text, for transcripts. */
export type ItemKind = Kind | 'text';

export type JobStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled';

/** One job of GET /api/mobile/jobs (backend/scene/api/mobile.py, from JobManager.snapshot in jobs.py). */
export type Job = {
  id: string;
  name: string;
  workflow: string;
  kind: Kind | string;
  status: JobStatus;
  created: number;
  started: number | null;
  finished: number | null;
  est_seconds: number | null;
  eta_seconds: number | null;
  step: number;
  steps: number;
  node: string;
  clip: number;
  clips: number;
  /** Place in line while queued (1 = next). */
  position: number | null;
  /** Why it failed, in words for its owner. */
  reason?: string;
  cost: number;
  project_id: number | null;
  prompt: string;
  workflow_title: string;
  /** The library items it made, once done. */
  items: { id: number; kind: ItemKind }[];
};

export type JobsAnswer = { jobs: Job[]; paused: boolean };

/** One item of GET /api/mobile/library and GET /api/mobile/library/{id} (mobile._slim_item). */
export type LibraryItem = {
  id: number;
  name: string;
  kind: ItemKind;
  workflow: string;
  workflow_title: string;
  prompt: string;
  seconds: number | null;
  size: number | null;
  created: number;
  /** 1 = starred (best take), -1 = thumbs down, 0 = none. */
  rating: number;
  project_id: number | null;
  project_name: string | null;
  public_id: string;
  job_id: string | null;
  cost: number | null;
  width?: number | null;
  height?: number | null;
  orientation?: string | null;
  /** The file's extension, like ".mp4". */
  ext: string;
  mine: boolean;
  made_by?: string;
};

export type LibraryPage = { items: LibraryItem[]; next_offset: number | null };

/** A setting of a workflow the phone offers (GET /api/mobile/workflows). */
export type Control = {
  id: string;
  type: 'text' | 'int' | 'float' | 'bool' | 'choice' | string;
  role: 'prompt' | 'duration' | null | string;
  label: string;
  default: unknown;
  choices?: (string | number)[] | null;
};

export type Option = {
  id: string;
  label: string;
  default: string;
  choices: { id: string; label: string; hint?: string }[];
};

export type Workflow = {
  id: string;
  kind: Kind;
  title: string;
  description: string;
  hints: string[];
  controls: Control[];
  options: Option[];
  size: { orientation: string; resolution: number } | null;
  resolutions: number[];
  /** It can be made without words (it works from its references). */
  prompt_optional: boolean;
  /** The pictures, videos or sounds it is given; optional false for the ones it needs. */
  refs: { id: string; kind: 'image' | 'video' | 'audio' | string; label: string; optional: boolean }[];
};

/** What POST /api/estimate and POST /api/jobs take (studio.py). */
export type JobSettings = {
  workflow: string;
  values: Record<string, unknown>;
  /** A reference slot filled with a library item: the studio keeps it and sends it to the provider when the job runs
   *  (POST /api/library/{id}/reference). */
  refs?: Record<string, { comfy_name: string; name: string }>;
  project_id?: number | null;
  options?: Record<string, string>;
  resolution?: number;
  orientation?: string;
  name?: string;
};

/** POST /api/estimate. */
export type Estimate = {
  credits: number;
  minutes: number | null;
  seconds: number | null;
  text: string;
  /** Price of each choice of an option, e.g. {quality: {draft: 20, final: 40}}. */
  choices: Record<string, Record<string, number>>;
  balance: number;
  resolution_note: string;
};

/** GET /api/mobile/credits. */
export type Credits = {
  balance: number;
  events: { amount: number; reason: string; note: string | null; created: number; job_name: string | null }[];
};

/** POST /api/devices, GET /api/devices (api/devices.py). */
export type Device = {
  token: string;
  platform: string;
  notify_done: boolean;
  notify_failed: boolean;
};

/** GET /api/status (studio.py): the version of the page files (when the build was written, in seconds), so an open tab
 *  knows a newer page is out. */
export type Status = { page?: number };

/** GET /api/announcement: the admins' message to everyone, if any. */
export type Announcement = { text?: string; level?: string; until?: number | null; maintenance?: boolean };

/** One row of GET /api/projects (api/library.list_projects): a project, or a module (parent_id set). */
export type ProjectRow = {
  id: number;
  ref: string;
  name: string;
  canvas_name: string | null;
  created: number;
  parent_id: number | null;
  parent_name: string | null;
  parent_ref: string | null;
  members: number;
  /** How many modules a project has (0 for a module). */
  modules: number;
  items: number;
  cover_id: number | null;
  cover_kind: ItemKind | null;
  updated: number | null;
  role: 'owner' | 'manager' | 'creator' | 'viewer' | string;
  /** Whose project it is, when it was shared with you. */
  owner_name?: string;
};

/** A module as GET /api/projects/{id} lists it; the project's own canvas comes first with main: true. */
export type ModuleRow = {
  id: number;
  ref: string;
  name: string;
  created: number;
  main: boolean;
  items: number;
  updated: number | null;
  cover_id: number | null;
  cover_kind: ItemKind | null;
};

export type Member = { user_id: number; name: string; email?: string; role: string };

/** GET /api/projects/{id}. */
export type ProjectDetail = {
  project: {
    id: number;
    ref: string;
    name: string;
    created: number;
    role: string;
    members: Member[];
    items: number;
    updated: number | null;
    cover_id: number | null;
    cover_kind: ItemKind | null;
  };
  modules: ModuleRow[];
};

/** GET /api/mobile/modules/{id} (api/mobile.mobile_module): a module laid out for a phone. */
export type ModuleView = {
  module: {
    id: number;
    ref: string;
    name: string;
    main: boolean;
    role: string;
    project: { id: number; ref: string; name: string };
  };
  /** The story, in shot order; each shot's takes newest first. */
  shots: { number: number; takes: LibraryItem[] }[];
  /** Named boards (Outputs first), each with stacks of versions, newest first. */
  boards: { name: string; stacks: { group: string; shot_number: number | null; items: LibraryItem[] }[] }[];
  items: number;
  updated: number | null;
};

/** GET /api/skills (api/workspace.list_skills). */
export type Skill = {
  id: string;
  title: string;
  version: number;
  desc: string;
  /** The recipe, in Markdown. */
  text: string;
  words: string;
  next: string[];
  /** A craft skill: how to direct, cover, keep continuity (as opposed to a workflow recipe). */
  craft: boolean;
};

/** A plan of the agent's that waits for approval (GET /api/mobile/waiting). */
export type WaitingPlan = {
  project_id: number;
  module: string;
  project: string;
  tab: string;
  tab_name: string;
  instruction: string;
  reply: string;
  steps: number;
  total: number;
  at: number | null;
};

/** A NeuralCore entry (GET /api/kit, memory.kit_row): a character, place, prop... the agent keeps the same. */
export type KitEntry = {
  id: number;
  name: string;
  tag: string;
  type: 'character' | 'location' | 'outfit' | 'prop' | 'voice' | 'style' | 'script' | 'other' | string;
  kind: string;
  about: string;
  use_note: string | null;
  always: boolean;
  hidden: boolean;
  url: string;
  variant: string;
  palette: string;
};
