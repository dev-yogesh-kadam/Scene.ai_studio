// The user's own choices, kept on the server so they follow the user to any browser (S2, X3): the agent's model, its
// effort per model, whether a plan runs without Approve, and the "explain" switch per conversation; the workflow used
// last for each kind, the kind and the project Create opened on, and the skills used lately. Loaded once the user is
// known (SessionGate waits for it), read at once by whoever needs them, and saved as they change. Choices this browser
// kept before (localStorage) are sent once, for whatever the server does not have yet, and then forgotten here.

import { useSyncExternalStore } from 'react';
import { agentPreferences, setAgentPreferences, type AgentPreferences } from '@scene/shared/api/agent';
import { setStudioPreferences, studioPreferences, type StudioPreferences } from '@scene/shared/api/preferences';
import { prefs } from '../common/prefs';

const AGENT: AgentPreferences = { retry_once: false, model: null, effort: {}, permission: 'always', explain: {} };
const STUDIO: StudioPreferences = { workflows: {}, kind: null, project: null, skills: [], seen: [] };

let agent = AGENT;
let studio = STUDIO;
let version = 0;
const listeners = new Set<() => void>();
const changed = () => {
  version += 1;
  for (const fn of listeners) fn();
};

/** What this browser kept before the choices moved to the server: sent once where the server has nothing yet. */
function fromThisBrowser(server: { agent: AgentPreferences; studio: StudioPreferences }) {
  const keys = prefs.keys().filter((k) => k.startsWith('scene.'));
  const value = (key: string) => prefs.get(key) || null;
  const under = (start: string) =>
    Object.fromEntries(keys.filter((k) => k.startsWith(start)).map((k) => [k.slice(start.length), prefs.get(k)]));
  const toAgent: Partial<AgentPreferences> = {};
  const toStudio: Partial<StudioPreferences> = {};
  // a model picked before 17 October was forgotten then (scene.agent.model.v): only a later one is kept
  const model = prefs.get('scene.agent.model.v') === '2' ? value('scene.agent.model') : null;
  if (model && !server.agent.model) toAgent.model = model;
  const effort = under('scene.agent.effort.');
  if (Object.keys(effort).length && !Object.keys(server.agent.effort).length) toAgent.effort = effort;
  const permission = value('scene.agent.permission');
  if ((permission === 'all' || permission === 'videos') && server.agent.permission === 'always')
    toAgent.permission = permission;
  const explain = Object.fromEntries(Object.entries(under('scene.agent.explain.')).map(([k, v]) => [k, v === '1']));
  if (Object.keys(explain).length && !Object.keys(server.agent.explain).length) toAgent.explain = explain;
  const workflows = under('scene.workflow.');
  if (Object.keys(workflows).length && !Object.keys(server.studio.workflows).length) toStudio.workflows = workflows;
  const kind = value('scene.kind');
  if (kind && !server.studio.kind) toStudio.kind = kind;
  const project = Number(value('scene.project')) || null;
  if (project && server.studio.project == null) toStudio.project = project;
  try {
    const skills = JSON.parse(prefs.get('scene.agent.skills.recent', '[]')) as unknown;
    if (Array.isArray(skills) && skills.length && !server.studio.skills.length)
      toStudio.skills = skills.filter((s): s is string => typeof s === 'string');
  } catch {
    // not readable: nothing to keep
  }
  const moved = [
    'scene.agent.model',
    'scene.agent.model.v',
    'scene.agent.permission',
    'scene.kind',
    'scene.project',
    'scene.agent.skills.recent',
    ...keys.filter((k) => /^scene\.(agent\.effort|agent\.explain|workflow)\./.test(k)),
  ];
  return { toAgent, toStudio, moved };
}

export const userPrefs = {
  agent: () => agent,
  studio: () => studio,

  /** The user's choices from the server; with none to be had (offline), the defaults. */
  async load() {
    try {
      const [a, s] = await Promise.all([agentPreferences(), studioPreferences()]);
      agent = a;
      studio = s;
      const { toAgent, toStudio, moved } = fromThisBrowser({ agent: a, studio: s });
      if (Object.keys(toAgent).length) agent = await setAgentPreferences(toAgent);
      if (Object.keys(toStudio).length) studio = await setStudioPreferences(toStudio);
      for (const key of moved) prefs.remove(key);
    } catch {
      agent = AGENT;
      studio = STUDIO;
    }
    changed();
  },

  /** The agent's settings as the server answered a change made elsewhere. */
  saved(found: AgentPreferences) {
    agent = found;
    changed();
  },

  /** Change some of the agent's settings: at once here, and on the server. */
  setAgent(patch: Partial<AgentPreferences>) {
    agent = {
      ...agent,
      ...patch,
      effort: { ...agent.effort, ...patch.effort },
      explain: { ...agent.explain, ...patch.explain },
    };
    changed();
    void setAgentPreferences(patch).catch(() => {}); // kept here for this visit either way
  },
  setStudio(patch: Partial<StudioPreferences>) {
    const next = { ...studio, ...patch, workflows: { ...studio.workflows, ...patch.workflows } };
    if (JSON.stringify(next) === JSON.stringify(studio)) return; // as it was: nothing to save
    studio = next;
    changed();
    void setStudioPreferences(patch).catch(() => {});
  },

  subscribe(fn: () => void) {
    listeners.add(fn);
    return () => void listeners.delete(fn);
  },
};

/** Redraws when the user's choices change; returns them. */
export function useUserPrefs() {
  useSyncExternalStore(userPrefs.subscribe, () => version);
  return { agent, studio };
}
