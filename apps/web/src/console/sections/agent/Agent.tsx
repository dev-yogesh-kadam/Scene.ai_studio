// The console's Agent section: how the agent's models did (by model, by what they were asked for), its latest runs with
// every call and its words, a replay with another model, and the models of its roles. See backend/scene/traces.py.

import { useState } from 'react';
import { api } from '../../../common/api';
import { Field } from '../../../common/components/AuthForm';
import { Segmented } from '../../../common/components/Segmented';
import { useFilters, useNotice, useSection } from '../shared/context';
import { Loaded, Notice, Person, Table, Tile, ago, number, span } from '../shared/ui';
import { RunDrawer, TraceLink, tokens, type Langfuse, type RunRow } from './RunDrawer';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../shared/Console.module.css';
import css3 from '../../../studio/pages/create/CreatePage.module.css';
const css = classesOf(css0, css1, css2, css3);

const ROLES = [
  {
    id: 'main',
    label: 'Main model',
    hint: 'Plans and answers when the user picks none.',
    none: 'the first one there is',
  },
  {
    id: 'fast',
    label: 'Fast model',
    hint: 'The small jobs: image captions, notes, the check of a skill.',
    none: 'the model in use',
  },
];

type Stat = {
  model?: string;
  purpose?: string;
  calls: number;
  errors: number;
  avg_seconds: number;
  tokens_per_second?: number;
  prompt_tokens: number;
  answer_tokens: number;
};
type Report = {
  days: number;
  totals: Partial<Stat>;
  by_model: Stat[];
  by_purpose: Stat[];
  runs: RunRow[];
  models: string[];
  roles: Record<string, string>;
  configured: Record<string, string>;
  langfuse: Langfuse | null;
};

function StatsTable({ rows, first }: { rows: Stat[]; first: string }) {
  return (
    <Table
      head={[first, 'Calls', 'Failed', 'Average', 'Speed', 'Read', 'Written']}
      rows={rows.map((r) => [
        r.model || r.purpose || '(none)',
        number(r.calls),
        r.errors ? (
          <span key="e" className="error">
            {number(r.errors)}
          </span>
        ) : (
          '0'
        ),
        span(r.avg_seconds),
        r.tokens_per_second ? `${r.tokens_per_second} tok/s` : '',
        tokens(r.prompt_tokens),
        tokens(r.answer_tokens),
      ])}
      empty="No calls in this period."
    />
  );
}

function RolesCard({ report }: { report: Report }) {
  const [values, setValues] = useState(report.roles);
  const { notice, run } = useNotice();
  return (
    <div className={css('card')}>
      <div className={css('card-head')}>
        <h2>Models for each role</h2>
      </div>
      <p className="muted small">
        {report.models.length
          ? `Any of the ${report.models.length} Claude models set up now. Empty follows config.json.`
          : 'Claude Code is not set up on the studio PC, so no list: a model can still be named. Empty follows config.json.'}
      </p>
      <datalist id="agent-models">
        {report.models.map((m) => (
          <option key={m} value={m} />
        ))}
      </datalist>
      {ROLES.map((r) => (
        <Field key={r.id} label={r.label}>
          <input
            type="text"
            list="agent-models"
            value={values[r.id] ?? ''}
            placeholder={`config.json: ${report.configured[r.id] || r.none}`}
            onChange={(e) => setValues((was) => ({ ...was, [r.id]: e.target.value }))}
          />
          <div className="muted small">{r.hint}</div>
        </Field>
      ))}
      <Notice notice={notice} />
      <div className="row" style={{ marginTop: 12 }}>
        <button
          className="btn primary"
          onClick={() =>
            void run(async () => {
              await api('/api/admin/agent/roles', { method: 'PUT', json: values });
              return 'Saved. The agent uses them from its next call.';
            })
          }
        >
          Save
        </button>
      </div>
    </div>
  );
}

export default function Agent() {
  const [s, set] = useFilters<{ days: number }>('agent');
  const [open, setOpen] = useState<RunRow | null>(null);
  const query = useSection('agent', [s.days], () => api<Report>('/api/admin/agent?days=' + s.days));
  return (
    <Loaded query={query}>
      {(report) => {
        const t = report.totals;
        return (
          <>
            <div className="row" style={{ marginBottom: 12 }}>
              <span className="muted">Period</span>
              <Segmented
                choices={[
                  { id: 1, label: 'Today' },
                  { id: 7, label: '7 days' },
                  { id: 30, label: '30 days' },
                ]}
                current={report.days}
                onPick={(days) => set({ days })}
              />
            </div>
            <div className={css('tiles kpis')}>
              <Tile label="Calls to the models" value={number(t.calls || 0)} />
              <Tile
                label="Failed"
                value={number(t.errors || 0)}
                sub={t.calls ? Math.round((100 * (t.errors || 0)) / t.calls) + '% of them' : ''}
              />
              <Tile label="Average answer" value={span(t.avg_seconds) || '–'} />
              <Tile
                label="Writing speed"
                value={t.tokens_per_second ? `${t.tokens_per_second}` : '–'}
                sub="tokens a second"
              />
              <Tile
                label="Tokens"
                value={tokens((t.prompt_tokens || 0) + (t.answer_tokens || 0))}
                sub={`read ${tokens(t.prompt_tokens || 0)} · wrote ${tokens(t.answer_tokens || 0)}`}
              />
            </div>
            <div className={css('grid-2')}>
              <div className={css('card')}>
                <div className={css('card-head')}>
                  <h2>By model</h2>
                </div>
                <StatsTable rows={report.by_model} first="Model" />
              </div>
              <div className={css('card')}>
                <div className={css('card-head')}>
                  <h2>By what it was asked</h2>
                </div>
                <StatsTable rows={report.by_purpose} first="For" />
              </div>
            </div>
            <div className={css('grid-2')}>
              <div className={css('card')}>
                <div className={css('card-head')}>
                  <h2>Latest runs</h2>
                  <span className="muted small">a run: the calls of one request</span>
                </div>
                <Table
                  head={['When', 'Who', 'For', 'Model', 'Tools', 'Calls', 'Time', ...(report.langfuse ? [''] : [])]}
                  rows={report.runs.map((r) => [
                    ago(r.started),
                    r.user_name ? (
                      <Person key="p" name={r.user_name} email={r.user_email} />
                    ) : (
                      <span key="s" className="muted">
                        the studio
                      </span>
                    ),
                    r.purposes.join(', '),
                    <span key="m" className="small">
                      {r.models.join(', ')}
                    </span>,
                    <span key="t" className="small">
                      {r.tools.join(', ')}
                    </span>,
                    r.errors ? (
                      <span key="e" className="error">
                        {`${r.calls} (${r.errors} failed)`}
                      </span>
                    ) : (
                      number(r.calls)
                    ),
                    span(r.seconds),
                    ...(report.langfuse
                      ? [<TraceLink key="l" langfuse={report.langfuse} trace={r.trace} label="Langfuse" />]
                      : []),
                  ])}
                  onRow={(i) => setOpen(report.runs[i])}
                  empty="No calls yet. They appear as people use the agent."
                />
                <p className="muted small" style={{ marginTop: 10 }}>
                  Each call is kept for 30 days; its words (what was sent and the answer) for a week, to read them again
                  or replay them with another model.
                </p>
              </div>
              <RolesCard key={JSON.stringify(report.roles)} report={report} />
            </div>
            {open && <RunDrawer run={open} models={report.models} onClose={() => setOpen(null)} />}
          </>
        );
      }}
    </Loaded>
  );
}
