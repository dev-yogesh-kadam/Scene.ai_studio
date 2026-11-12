// One conversation with the agent (a tab of the panel): its turns, what is happening to them, and the choices made for
// it. The turns are the objects kept on the board and are changed in place, as they always were; every change says so
// (`changed`), and the components draw from here (useConversation). Nothing here touches the page.

import { compactDirection, setAgentPreferences } from '@scene/shared/api/agent';
import { putBoard } from '@scene/shared/api/canvas';
import type { IconName } from '../../../common/components/Icon/Icon';
import type { Item } from '../../../common/media/item';
import { userPrefs } from '../../userPrefs';
import { KEPT, RECALLED, spentBy, takesOf } from './shots';
import type { Job, Models, Pending, Run, ServerPlan, Spent, Typed } from './types';

// Whether a plan runs as soon as it arrives or waits for Approve. The choice is the user's, kept on the server, which
// holds the page's own approvals to it (userPrefs).
export const PERMISSIONS: { id: string; icon: IconName; label: string; about: string }[] = [
  {
    id: 'all',
    icon: 'forward',
    label: 'Allow all',
    about: 'Never asks. Plans run at once; a failed shot is made again up to 3 times, then the best take goes on.',
  },
  { id: 'videos', icon: 'handvideo', label: 'Ask before videos', about: 'Runs images and audio. Asks before videos.' },
  { id: 'always', icon: 'hand', label: 'Always ask', about: 'Asks before every generation.' },
];
export const EFFORT_NAMES: Record<string, string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  xhigh: 'Extra high',
  max: 'Max',
};

export type ChatEnv = {
  project: () => number;
  session: string | null; // the agent tab this conversation is
  tabName: () => string;
  selection: () => Item[];
  onJobs: (ids: string[]) => void;
  onSaved: (saved: { spent: Spent; updated: number | null }) => void;
  onFocus: (id: number) => void;
  locate: (id: number) => { shot: string; take: number } | null;
  onUploaded: () => void;
  setBalance: (credits: number) => void; // what a message cost, as its answer says
  queued: () => void; // jobs were added: look at the queue now
};

/** The message box, as the conversation needs it. */
export type Box = {
  read: () => Typed;
  clear: () => void;
  snapshot: () => unknown;
  restore: (saved: unknown) => void;
  focus: () => void;
};

export class AgentChat {
  direction = ''; // the durable notes of this conversation (the film, the style, the shot list), kept beside the turns
  folded = 0; // how many turns from the start are folded into the direction and no longer sent
  chatWorkflows: string[] = []; // the video and image workflows this chat is pinned to; none: the agent chooses
  runs: Run[] = [];
  busy = false; // a message is with the model
  pending: Pending | null = null; // the message being answered
  working = false; // an approved plan is being carried out
  halted = false; // Stop generation was pressed: the plan being carried out goes no further
  boarding = false; // a storyboard or an animation is being planned
  collecting = false;
  reservedCredits = 0; // promised to auto-retakes queued in this burst of reviews, not yet off the balance
  jobs: Job[] = [];
  credits = 0;
  plans = new Map<number, ServerPlan>();
  status = { text: 'checking…', hidden: false, error: false, title: '' }; // the model's name, or why it is offline
  models: Models = { list: [], current: null, prices: {}, byTokens: [], efforts: {}, shown: (name) => name };
  version = 0;
  box: Box | null = null;
  follow = 0; // something new arrived: the log goes to its end when this changes
  private listeners = new Set<() => void>();
  private flash: ReturnType<typeof setTimeout> | undefined;
  env: ChatEnv;
  readonly send: (typed?: Typed) => Promise<void>;
  readonly talk: string; // the board this conversation is kept in

  constructor(session: string | null, send: (chat: AgentChat, typed?: Typed) => Promise<void>) {
    this.env = {
      session,
      project: () => 0,
      tabName: () => '',
      selection: () => [],
      onJobs: () => {},
      onSaved: () => {},
      onFocus: () => {},
      locate: () => null,
      onUploaded: () => {},
      setBalance: () => {},
      queued: () => {},
    };
    this.send = (typed) => send(this, typed);
    this.talk = session ? 'agent-' + session : 'agent';
  }

  /** What the page around it says and is told; set again on every drawing. */
  setEnv(env: Omit<ChatEnv, 'session'>) {
    this.env = { ...env, session: this.env.session };
  }
  /** The live connection's latest. */
  setJobs(jobs: Job[]) {
    this.jobs = jobs;
  }
  setCredits(credits: number) {
    this.credits = credits;
    this.changed();
  }

  /** Explain more: replies teach the craft. Kept per conversation. */
  get explain() {
    return !!userPrefs.agent().explain[this.env.session || 'main'];
  }

  subscribe = (fn: () => void) => {
    this.listeners.add(fn);
    return () => void this.listeners.delete(fn);
  };
  getVersion = () => this.version;

  changed = (follow = false) => {
    this.version += 1;
    if (follow) this.follow += 1;
    for (const fn of [...this.listeners]) fn();
  };

  /** Change a turn, a step or a take, and draw again; `keep`: the conversation is saved too. */
  patch<T extends object>(target: T, change: Partial<T>, keep = false) {
    Object.assign(target, change);
    if (keep) void this.save();
    this.changed();
  }

  /** The state kept on a turn's `ui`, made when first asked for. */
  stateOf<K extends keyof Run['ui']>(
    run: Run,
    key: K,
    made: () => NonNullable<Run['ui'][K]>,
  ): NonNullable<Run['ui'][K]> {
    const ui = (run.ui = run.ui || {});
    return (ui[key] ??= made()) as NonNullable<Run['ui'][K]>;
  }

  save() {
    this.env.onSaved({ spent: spentBy(this.runs, this.jobs), updated: Date.now() });
    const drop = Math.max(0, this.runs.length - KEPT);
    const project = this.env.project() || null;
    return putBoard(this.talk, project, {
      runs: this.runs.slice(-KEPT),
      direction: this.direction,
      folded: Math.max(0, this.folded - drop),
      workflows: this.chatWorkflows,
    }).catch(() => {});
  }

  /** A short word in the place of the model's name, then the name again. */
  say(text: string) {
    const was = this.status;
    clearTimeout(this.flash);
    this.status = { ...was, text, hidden: false };
    this.changed();
    this.flash = setTimeout(() => {
      this.status = was;
      this.changed();
    }, 4000);
  }

  private history(runs: Run[]) {
    return runs
      .filter((r) => !r.error)
      .map((r) => ({
        instruction: r.instruction,
        reply: r.reply,
        steps: r.steps.map((s) => ({ name: s.name, uses: (s.uses || []).map((u) => u.name) })),
      }));
  }
  /** The turns sent along with a message: the newest ones, less those already folded into the direction. */
  recalled() {
    return this.history(this.runs.slice(Math.max(this.folded, this.runs.length - RECALLED)));
  }

  /** Fold the conversation so far into the direction, so the agent keeps the whole of it in a few lines. */
  async compact() {
    if (!this.runs.length) return;
    if (this.busy) return this.say('The agent is working. Fold the conversation when it has finished.');
    try {
      const done = await compactDirection({
        direction: this.direction,
        model: userPrefs.agent().model,
        history: this.history(this.runs),
      });
      this.direction = done.direction;
      this.folded = Math.max(this.folded, this.runs.length - 2); // the last two turns stay as they are
      void this.save();
      this.say('Conversation folded into the direction.');
    } catch (e) {
      this.say((e as Error).message);
    }
  }

  startedJobs() {
    return this.runs
      .flatMap((r) => r.steps.flatMap((s) => takesOf(s).map((t) => t.job)))
      .filter((id): id is string => !!id);
  }
  jobOf(id: string | null | undefined) {
    return id ? this.jobs.find((j) => j.id === id) : undefined;
  }
  /** While an approved plan is being made the agent is busy: the box waits and Send becomes Stop generation. */
  activeJobs() {
    return this.startedJobs().filter((id) => {
      const job = this.jobOf(id);
      return job && (job.status === 'queued' || job.status === 'running');
    });
  }
  generating() {
    return this.working || this.activeJobs().length > 0;
  }
  /** A line of the work done for a plan after it was approved: queued, waited, ready, checked. */
  work(run: Run, icon: string, text: string) {
    (run.work = run.work || []).push({ icon, text, at: Date.now() });
  }

  permission() {
    return PERMISSIONS.find((p) => p.id === userPrefs.agent().permission) || PERMISSIONS[2];
  }
  setPermission(id: string) {
    if (id === 'all' || id === 'videos' || id === 'always') userPrefs.setAgent({ permission: id });
    this.changed();
  }
  /** A failed shot is made again once by itself (off unless the user turned it on). */
  get retryOnce() {
    return userPrefs.agent().retry_once;
  }
  async setRetryOnce(on: boolean) {
    try {
      userPrefs.saved(await setAgentPreferences({ retry_once: on }));
    } catch (e) {
      this.say((e as Error).message);
    }
    this.changed();
  }
  toggleExplain() {
    userPrefs.setAgent({ explain: { [this.env.session || 'main']: !this.explain } });
    this.say(
      this.explain
        ? 'Explain more is on: from the next reply the agent says why it chose each thing.'
        : 'Explain more is off: replies stay brief.',
    );
    this.changed();
  }
  setPins(ids: string[]) {
    this.chatWorkflows = ids;
    void this.save();
    this.changed();
  }

  priceText(name: string | null) {
    const { prices, byTokens } = this.models;
    return name && prices[name]
      ? `${prices[name]} cr a message`
      : name && byTokens.includes(name)
        ? 'Charged by tokens'
        : 'Free';
  }
  effortsOf(name: string | null) {
    return (name && this.models.efforts[name]) || { levels: [] as string[], default: null };
  }
  /** How hard the model thinks: the levels it takes, kept per model. Low until the user picks another. */
  effortOf(name: string | null) {
    const { levels } = this.effortsOf(name);
    const picked = (name && userPrefs.agent().effort[name]) || '';
    return levels.includes(picked) ? picked : levels.includes('low') ? 'low' : levels[0] || '';
  }
  setEffort(level: string) {
    if (this.models.current) userPrefs.setAgent({ effort: { [this.models.current]: level } });
    this.changed();
  }
  setModel(name: string) {
    this.models = { ...this.models, current: name };
    userPrefs.setAgent({ model: name });
    this.changed();
  }
}
