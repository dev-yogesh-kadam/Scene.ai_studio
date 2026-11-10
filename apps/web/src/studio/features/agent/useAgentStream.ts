// A message to the agent, answered as it works: one JSON object a line (NDJSON). The message goes into the log at once
// with the agent's work under it as it happens; the box empties and waits. Stop brings the message back to be changed.

import { useCallback } from 'react';
import { planMessage } from '@scene/shared/api/agent';
import { userPrefs } from '../../userPrefs';
import { approve } from './actions';
import type { AgentChat } from './chat';
import { carryOn } from './checks';
import { GO } from './shots';
import type { Activity, Chips, Question, Run, RunContext, Step, Typed } from './types';

type Answer = {
  reply: string;
  thought?: string;
  activity?: Activity[];
  seconds?: number;
  chips?: Chips;
  memory_used?: string[];
  content_note?: string;
  steps: Step[];
  total: number;
  llm?: Run['llm'];
  question?: Question | null;
  questions?: Question[];
  continues?: boolean;
  context?: RunContext | null;
  direction?: string;
  balance?: number;
};

/** `typed`: a message that did not come from the box (a change asked for under a plan); the box is then left alone. */
export async function sendMessage(chat: AgentChat, typed?: Typed) {
  const fromBox = !typed;
  const message = typed ?? chat.box?.read();
  if (!message) return;
  const { text, shown: instruction, ids: attached, parts } = message;
  if (!text || chat.busy || chat.generating()) return;
  // Nothing attached: the canvas selection goes along, and the server reads it only when the words point at it.
  const ids =
    attached.length || !fromBox
      ? attached
      : chat.env
          .selection()
          .map((item) => item.id)
          .slice(0, 8);
  // "approve", "go ahead" typed under a plan that waits for approval is the Approve button: the agent can only propose.
  const waiting = chat.runs[chat.runs.length - 1];
  if (fromBox && waiting && waiting.state === 'proposed' && !chat.working && GO.test(text)) {
    if (waiting.total > chat.credits) return; // the button is off too: the cost is shown under the plan
    chat.box?.clear();
    return approve(chat, waiting);
  }
  chat.busy = true;
  const boxed = fromBox ? chat.box?.snapshot() : null;
  const controller = new AbortController();
  const auto = !!typed?.auto; // the studio carries a run on by itself: not a message the user wrote
  const pending = {
    instruction,
    parts,
    auto,
    stop: () => controller.abort(),
    events: [] as Activity[],
    status: 'Thinking',
    started: Date.now(),
  };
  chat.pending = pending;
  for (const r of chat.runs) if (r.ui) r.ui.more = false; // a new message folds every earlier long reply
  if (fromBox) chat.box?.clear();
  chat.changed(true);
  let made: Run | null = null;
  try {
    let found: Answer | null = null;
    await planMessage(
      {
        instruction: text,
        project_id: chat.env.project() || null,
        selection: ids,
        model: userPrefs.agent().model,
        effort: chat.effortOf(chat.models.current) || null,
        direction: chat.direction,
        run: chat.env.session || 'main',
        tab: chat.env.tabName(),
        explain: chat.explain,
        workflows: chat.chatWorkflows,
        history: chat.recalled(),
      },
      controller.signal,
      (event) => {
        if (event.type === 'error') throw new Error(String(event.message));
        if (event.type === 'plan') found = event as unknown as Answer;
        else if (event.type === 'status') pending.status = String(event.text);
        else pending.events.push(event as unknown as Activity);
        chat.changed();
      },
    );
    const answer = found as Answer | null;
    if (!answer) throw new Error('The agent stopped before it finished. Try again.');
    made = {
      instruction,
      parts,
      auto,
      reply: answer.reply,
      thought: answer.thought,
      activity: answer.activity || [],
      seconds: answer.seconds,
      chips: answer.chips || {},
      memoryUsed: answer.memory_used || [],
      contentNote: answer.content_note || '',
      steps: answer.steps,
      total: answer.total,
      state: answer.steps.length ? 'proposed' : 'answered',
      at: Date.now(),
      ui: {},
      llm: answer.llm || null,
      question: answer.question || null,
      questions: answer.questions || [],
      continues: !!answer.continues,
      context: answer.context || null,
    };
    if (answer.direction) chat.direction = answer.direction; // the agent kept its notes up to date
    if (answer.balance != null) {
      chat.credits = answer.balance; // the message itself may have cost credits
      chat.env.setBalance(answer.balance);
    }
    chat.runs.push(made);
    void chat.save();
  } catch (e) {
    if ((e as Error).name === 'AbortError') {
      // stopped: the message comes back to be changed or sent again
      if (fromBox) chat.box?.restore(boxed);
      else if (typed?.from) {
        typed.from.state = 'proposed';
        typed.from.revised = null;
        typed.from.ui.note = instruction;
        void chat.save();
      }
    } else
      chat.runs.push({
        instruction,
        parts,
        reply: (e as Error).message,
        error: true,
        activity: pending.events,
        steps: [],
        total: 0,
        state: 'answered',
        at: Date.now(),
        ui: {},
      });
  }
  chat.busy = false;
  chat.pending = null;
  chat.changed(true);
  chat.box?.focus();
  // The permission chosen under the box: a plan may run at once, without waiting for Approve.
  if (made && made.steps.length && !chat.working && made.total <= chat.credits) {
    const mode = chat.permission().id;
    if (mode === 'all' || (mode === 'videos' && !made.steps.some((s) => s.kind === 'video')))
      void approve(chat, made, true);
  }
  if (made && !made.steps.length && made.continues) setTimeout(() => carryOn(chat), 1500); // it saved its work: the run goes on
}

/** Send, or stop what is being answered. */
export function useAgentStream(chat: AgentChat) {
  const send = useCallback(() => void chat.send(), [chat]);
  const stop = useCallback(() => chat.pending?.stop(), [chat]);
  return { send, stop };
}
