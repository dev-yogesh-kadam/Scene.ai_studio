// One conversation for a tab of the panel: made once, loaded from its board, kept current with the live connection
// (the jobs and the balance), and drawn again whenever it changes.

import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useLayoutEffect, useState, useSyncExternalStore } from 'react';
import { agentStatus } from '@scene/shared/api/agent';
import { getBoard } from '@scene/shared/api/canvas';
import type { Item } from '../../../common/media/item';
import { userPrefs } from '../../userPrefs';
import { JOBS, useJobs } from '../../live';
import { useSession } from '../../session';
import { followPlans } from './actions';
import { AgentChat } from './chat';
import { carryOn, collectResults, reviewFinished } from './checks';
import { spentBy } from './shots';
import type { Job, Run, Spent } from './types';
import { sendMessage } from './useAgentStream';
import { usePlanProgress } from './usePlanProgress';

export type ConversationProps = {
  project: number;
  session: string;
  tabName: () => string;
  selection: () => Item[];
  onJobs: (ids: string[]) => void;
  onSaved: (saved: { spent: Spent; updated: number | null }) => void;
  onFocus: (id: number) => void;
  locate: (id: number) => { shot: string; take: number } | null;
  onUploaded: () => void;
};

type Saved = { runs?: Run[]; direction?: string; folded?: number; workflows?: unknown[] };

async function load(chat: AgentChat) {
  const project = chat.env.project();
  try {
    const [saved, state] = await Promise.all([getBoard<Saved>(chat.talk, project), agentStatus()]);
    const data = saved.data ?? {};
    chat.runs = data.runs || [];
    chat.direction = data.direction || '';
    chat.folded = Math.min(data.folded || 0, chat.runs.length);
    chat.chatWorkflows = Array.isArray(data.workflows)
      ? data.workflows.filter((w): w is string => typeof w === 'string')
      : [];
    followPlans(chat);
    chat.env.onSaved({ spent: spentBy(chat.runs, chat.jobs), updated: null }); // what it spent, without counting as use
    for (const run of chat.runs) {
      run.ui = run.ui || {};
      for (const step of run.steps) {
        // nothing is under way after a reload
        step.waiting = false;
        step.rendering = false;
        step.reviewing = false;
        step.updating = false;
        step.editing = false;
        if (step.take2) step.take2.reviewing = false;
      }
    }
    // The models there are, and what a message to each costs; offline, just why.
    const names = state.online ? state.models || [] : [];
    const picked = userPrefs.agent().model ?? '';
    const current = names.includes(picked) ? picked : state.model;
    // A hosted model is named "<service>/<name>"; it is shown as its name and the service it is asked of.
    const services = Object.fromEntries((state.hosted || []).map((s) => [s.id, s.name]));
    const shown = (name: string) => {
      const [sid, ...rest] = name.split('/');
      return rest.length && services[sid] ? `${rest.join('/')} · ${services[sid]}` : name;
    };
    chat.models = {
      list: names,
      current,
      prices: state.prices || {},
      byTokens: state.by_tokens || [],
      efforts: state.efforts || {},
      shown,
    };
    chat.status = {
      text: state.online ? shown(state.model) : 'offline',
      hidden: state.online && names.length > 0,
      error: !state.online,
      title: state.online ? '' : state.detail || '',
    };
    chat.env.onJobs(chat.startedJobs());
  } catch (e) {
    chat.status = { ...chat.status, text: (e as Error).message };
  }
  chat.changed(true);
  void collectResults(chat);
  carryOn(chat); // a run whose newest turn only saved its work goes on, also after a reload
}

export function useConversation(props: ConversationProps) {
  const client = useQueryClient();
  const { user, setUser } = useSession();
  const jobs = useJobs() as Job[];
  const [chat] = useState(() => new AgentChat(props.session, sendMessage));
  useLayoutEffect(() => {
    chat.setEnv({
      project: () => props.project,
      tabName: props.tabName,
      selection: props.selection,
      onJobs: props.onJobs,
      onSaved: props.onSaved,
      onFocus: props.onFocus,
      locate: props.locate,
      onUploaded: props.onUploaded,
      setBalance: (credits) => setUser((was) => ({ ...was, credits })),
      queued: () => void client.invalidateQueries({ queryKey: JOBS }),
    });
  });
  useSyncExternalStore(chat.subscribe, chat.getVersion);

  useEffect(() => {
    void load(chat);
    return userPrefs.subscribe(() => chat.changed()); // the model, effort, permission or explain changed
  }, [chat]);

  // The live connection: a shot the agent made has finished (it shows, and the agent looks at it); the balance moved.
  useEffect(() => {
    chat.setJobs(jobs);
    void collectResults(chat);
    reviewFinished(chat);
    carryOn(chat); // a long skill's plan has come to an end: the run goes on (a failed last step too)
    chat.env.onSaved({ spent: spentBy(chat.runs, chat.jobs), updated: null }); // a job that failed gave its credits back
    chat.changed();
  }, [chat, jobs]);
  useEffect(() => {
    chat.setCredits(Number(user.credits ?? 0));
  }, [chat, user.credits]);
  usePlanProgress(chat);
  return chat;
}
