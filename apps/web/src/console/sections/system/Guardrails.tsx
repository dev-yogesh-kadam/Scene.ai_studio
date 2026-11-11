// The guardrails card of the System section: the studio-wide stop (new agent turns and new renders refused at once)
// with what users are told, and the limits on spending and on the agent, each in its range. GET and PUT
// /api/admin/guardrails (backend/scene/guardrails.py, docs/guardrails.md).

import { useState } from 'react';
import { api } from '../../../common/api';
import { ask } from '../../../common/components/Dialog';
import { Field } from '../../../common/components/AuthForm';
import { useConsole, useNotice } from '../shared/context';
import { Facts, Notice, number, stamp } from '../shared/ui';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../shared/Console.module.css';
import css3 from '../../../studio/pages/create/CreatePage.module.css';
const css = classesOf(css0, css1, css2, css3);

export type Guardrails = {
  stop: { since: number; by?: string; text: string } | null;
  limits: Record<string, number>;
  ranges: Record<string, [number, number]>;
  defaults?: Record<string, number>;
  choices?: Record<string, string>; // the settings that are one of a few words (content_check_mode)
  options?: Record<string, string[]>;
};

/** What each choice is, and each of its words, in words; one the console does not know is shown by its name. */
const CHOICES: Record<string, { label: string; words: Record<string, string> }> = {
  content_check_mode: {
    label: 'Content check of each plan (the fast model, before Approve)',
    words: {
      off: 'Off: no check',
      warn: 'Warn: a note on the plan card',
      block: 'Block: refuse what it blocks, note the rest',
    },
  },
  creative_auto_review: {
    label: "Automatic review of big plans (a stronger model; the studio pays, not the user)",
    words: { on: 'On', off: 'Off: save the Claude usage' },
  },
};

/** What each limit is, in words; a limit the console does not know yet is shown by its name. */
const LIMITS: Record<string, { label: string; unit?: string }> = {
  guard_plan_max: { label: 'Credits one plan may reserve', unit: 'credits' },
  guard_run_max: { label: 'Credits one long run may spend', unit: 'credits' },
  guard_job_seconds: { label: 'Longest result one job may be priced for', unit: 'seconds' },
  guard_sessions_per_user: { label: 'Live agent sessions one user may hold' },
  guard_tool_calls: { label: 'Tool calls while the agent answers one message' },
  guard_turn_seconds: { label: 'Longest one message to the agent may take', unit: 'seconds' },
  creative_big_job_credits: { label: 'A plan priced above this is a big job (brief, concept, stills first)', unit: 'credits' },
};

/** A limit as typed, or the reason it can't be saved: a whole number in its range (0 is "no limit" where it may be). */
export function limitProblem(value: string, [low, high]: [number, number]): string | null {
  const n = Number(value);
  if (value.trim() === '' || !Number.isFinite(n)) return 'a number';
  if (!Number.isInteger(n)) return 'a whole number';
  if (n === 0 && low === 0) return null;
  if (n < low || n > high) return `${number(low)} to ${number(high)}`;
  return null;
}

export function GuardrailsCard({ g }: { g: Guardrails }) {
  const { refresh } = useConsole();
  const [text, setText] = useState(g.stop?.text ?? '');
  const [limits, setLimits] = useState(() =>
    Object.fromEntries(Object.entries(g.limits).map(([k, v]) => [k, String(v)])),
  );
  const { notice, run } = useNotice();
  const names = Object.keys(g.ranges);
  const problems = names
    .map((k) => [k, limitProblem(limits[k] ?? '', g.ranges[k])] as const)
    .filter(([, p]) => p !== null);
  const changed = names.filter((k) => Number(limits[k]) !== g.limits[k]);

  const put = (json: unknown, said: string) =>
    run(async () => {
      await api('/api/admin/guardrails', { method: 'PUT', json });
      await refresh();
      return said;
    });

  const stop = async () => {
    const yes = await ask({
      title: 'Stop the whole studio?',
      message:
        'Nobody can start a new message to the agent or a new render until you start it again. Renders already waiting do not start, and a running plan stops at its next step. Users are told your message.',
      confirm: 'Stop the studio',
      danger: true,
    });
    if (yes) await put({ stop: true, text }, 'Stopped. New work is refused.');
  };

  return (
    <div className={css('card')}>
      <div className={css('card-head')}>
        <h2>Guardrails</h2>
        <span className={css('pill ' + (g.stop ? 'failed' : 'done'))}>{g.stop ? 'Stopped' : 'Running'}</span>
      </div>
      <p className="muted small">
        The stop is the studio&apos;s emergency switch: it refuses new agent messages and new renders at once, for
        everyone. Maintenance (above) is for a planned restart. The limits apply to everyone but admins; changes take
        effect at once.
      </p>
      {g.stop && (
        <Facts
          pairs={[
            ['Stopped since', stamp(g.stop.since)],
            ['By', g.stop.by || '—'],
            ['Users are told', g.stop.text],
          ]}
        />
      )}
      <Field label="What users are told while it is stopped">
        <textarea
          rows={2}
          maxLength={300}
          placeholder="The studio has stopped new work for now. Try again later."
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </Field>
      <div className="row" style={{ marginTop: 8 }}>
        {g.stop ? (
          <>
            <button className="btn" onClick={() => void put({ stop: true, text }, 'Message saved.')}>
              Update message
            </button>
            <button className="btn primary" onClick={() => void put({ stop: false }, 'Started again.')}>
              Start the studio again
            </button>
          </>
        ) : (
          <button className="btn danger" onClick={() => void stop()}>
            Stop the studio
          </button>
        )}
      </div>
      <h3>Limits</h3>
      {names.map((k) => {
        const [low, high] = g.ranges[k];
        const about = LIMITS[k];
        const problem = limitProblem(limits[k] ?? '', g.ranges[k]);
        return (
          <Field key={k} label={about ? about.label + (about.unit ? ` (${about.unit})` : '') : k}>
            <input
              type="number"
              min={low}
              max={high}
              step={1}
              value={limits[k] ?? ''}
              aria-invalid={problem ? true : undefined}
              aria-description={`${number(low)} to ${number(high)}${low === 0 ? ', 0: no limit' : ''}`}
              onChange={(e) => setLimits({ ...limits, [k]: e.target.value })}
            />
          </Field>
        );
      })}
      <p className="muted small" style={{ marginTop: 6 }}>
        {names
          .map((k) => {
            const [low, high] = g.ranges[k];
            return `${LIMITS[k]?.label ?? k}: ${number(low)}–${number(high)}${low === 0 ? ' (0: no limit)' : ''}`;
          })
          .join(' · ')}
      </p>
      {problems.length > 0 && (
        <p className="notice error">{problems.map(([k, p]) => `${LIMITS[k]?.label ?? k} must be ${p}.`).join(' ')}</p>
      )}
      {Object.keys(g.options ?? {}).length > 0 && <h3>Checks</h3>}
      {Object.entries(g.options ?? {}).map(([k, words]) => (
        <Field key={k} label={CHOICES[k]?.label ?? k}>
          <select
            value={g.choices?.[k] ?? ''}
            onChange={(e) => void put({ choices: { [k]: e.target.value } }, 'Saved.')}
          >
            {words.map((w) => (
              <option key={w} value={w}>
                {CHOICES[k]?.words[w] ?? w}
              </option>
            ))}
          </select>
        </Field>
      ))}
      <Notice notice={notice} />
      <button
        className="btn primary"
        style={{ marginTop: 12 }}
        disabled={problems.length > 0 || changed.length === 0}
        onClick={() =>
          void put({ limits: Object.fromEntries(changed.map((k) => [k, Number(limits[k])])) }, 'Limits saved.')
        }
      >
        Save limits
      </button>
    </div>
  );
}
