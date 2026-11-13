// The admin console's Pricing section: what credits are worth, the rate of each kind of work, each workflow's own
// pricing, the credit packages, and the servers with what they draw.

import { useState } from 'react';
import { api } from '../../../common/api';
import { Field } from '../../../common/components/AuthForm';
import { useConsole, useNotice, useSection } from '../shared/context';
import { Loaded, Notice, Table, number } from '../shared/ui';
import { EditDialog, type Editing } from './EditDialog';
import { FactorsCard } from './Factors';
import { LlmCard, type Llm } from './LlmCard';
import { GROUPS, KINDS, rupees, trim, type Data, type Factors, type WorkflowRow } from './pricingData';
import { Packages, Servers } from './Lists';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared.module.css';
import css1 from '../../../common/components/Shared2.module.css';
import css2 from '../../../common/components/Shared3.module.css';
import css3 from '../shared/Console.module.css';
import css4 from '../../../studio/pages/create/CreatePage.module.css';
const css = classesOf(css0, css1, css2, css3, css4);

function Rates({ data }: { data: Data }) {
  const { refresh } = useConsole();
  const [value, setValue] = useState(String(data.inr_per_1000_credits));
  const [power, setPower] = useState(String(data.electricity_inr_per_kwh));
  const [dollar, setDollar] = useState(String(data.inr_per_usd));
  const [rates, setRates] = useState(() => Object.fromEntries(KINDS.map((k) => [k.id, String(data.rates[k.id])])));
  const { notice, run } = useNotice();
  const price = (credits: number) =>
    `${number(credits)} credits · ${rupees((credits * data.inr_per_1000_credits) / 1000)}`;
  return (
    <div className={css('card')}>
      <div className={css('card-head')}>
        <h2>Rates</h2>
      </div>
      <p className="muted small">
        What a user pays follows what they asked for, never how long the render took: a flat price for an image, a price
        per second of the result for everything else.
      </p>
      <div className={css('grid2')}>
        {KINDS.map((k) => (
          <Field key={k.id} label={`${k.label} (credits per ${data.per_job.includes(k.id) ? 'generation' : 'second'})`}>
            <input
              type="number"
              min={0}
              step="any"
              value={rates[k.id]}
              onChange={(e) => setRates((was) => ({ ...was, [k.id]: e.target.value }))}
            />
          </Field>
        ))}
        <Field label="Price of 1,000 credits (₹)">
          <input type="number" min={0} step="any" value={value} onChange={(e) => setValue(e.target.value)} />
        </Field>
      </div>
      <p className="muted small" style={{ marginTop: 8 }}>
        {`Now: an image costs ${price(data.rates.image)}, a 5-second video ${price(data.rates.video * 5)}, a minute of music ${price(data.rates.audio * 60)}.`}
      </p>
      <h3>Electricity</h3>
      <Field label="Price of electricity (₹ per kWh)">
        <input type="number" min={0} step="any" value={power} onChange={(e) => setPower(e.target.value)} />
      </Field>
      <p className="muted small" style={{ marginTop: 8 }}>
        Used for the running cost of each server below. It is never shown to users and does not change what they pay.
      </p>
      <h3>Claude</h3>
      <Field label="Rupees per US dollar (₹)">
        <input type="number" min={0} step="any" value={dollar} onChange={(e) => setDollar(e.target.value)} />
      </Field>
      <p className="muted small" style={{ marginTop: 8 }}>
        Claude&apos;s models are charged by the tokens each answer uses, at Anthropic&apos;s prices in dollars turned
        into rupees at this rate, then into credits. See Agent models below.
      </p>
      <Notice notice={notice} />
      <button
        className="btn primary"
        style={{ marginTop: 12 }}
        onClick={() =>
          void run(async () => {
            await api('/api/admin/pricing', {
              method: 'PUT',
              json: { inr_per_1000_credits: value, electricity_inr_per_kwh: power, inr_per_usd: dollar, rates },
            });
            await refresh();
          })
        }
      >
        Save
      </button>
    </div>
  );
}

function Workflows({ data, factors, edit }: { data: Data; factors: Factors; edit: (e: Editing) => void }) {
  const { refresh } = useConsole();
  const perJob = (kind: string) => data.per_job.includes(kind);
  const worth = (credits: number) => rupees((credits * data.inr_per_1000_credits) / 1000);
  const servers = [{ id: '', label: 'Any' }, ...data.servers.map((s) => ({ id: s.name, label: s.name }))];
  const rateText = (w: WorkflowRow) =>
    [w.base ? `${trim(w.base)} credits` : null, w.per_second ? `${trim(w.per_second)} credits/s` : null]
      .filter(Boolean)
      .join(' + ') || 'Free';
  const own = (w: WorkflowRow) => w.credits_per_second != null || w.base_credits != null;
  // A generation workflow's models, priced one by one at each resolution: credits a second for a video, a picture's
  // credits for a picture. The provider's own price is the hint, a starting point.
  const modelFields = (w: WorkflowRow) =>
    (w.models || []).flatMap((m) =>
      m.resolutions.map((r) => ({
        id: `model:${m.model}:${r}`,
        label: `${m.name} · ${r} (credits ${perJob(w.kind) ? 'a picture' : 'a second'})`,
        type: 'number' as const,
        hint: m.prices?.[r] != null ? `The provider charges ${trim(m.prices[r])}` : "Empty: the workflow's own rate",
      })),
    );
  const open = (w: WorkflowRow) =>
    edit({
      title: w.title,
      about: `${w.id}. Leave a rate empty to follow the rate for its type.${
        w.models?.length ? " Its models (the generation server's) are priced one by one below." : ''
      }`,
      fields: [
        {
          id: 'credits_per_second',
          label: 'Credits per second',
          type: 'number',
          hint: perJob(w.kind) ? 'None' : `${trim(data.rates[w.kind])} (the ${w.kind} rate)`,
        },
        {
          id: 'base_credits',
          label: 'Base credits per generation',
          type: 'number',
          hint: perJob(w.kind) ? `${trim(data.rates[w.kind])} (the ${w.kind} rate)` : 'None',
        },
        { id: 'resolution_multiplier', label: 'Resolution multiplier', type: 'number' },
        { id: 'quality_multiplier', label: 'Quality multiplier', type: 'number' },
        { id: 'preferred_server', label: 'Preferred server', type: 'choice', choices: servers },
        { id: 'fallback_servers', label: 'Fallback servers', type: 'text', hint: 'Names, separated by commas' },
        { id: 'enabled', label: 'Offered to users', type: 'check' },
        ...GROUPS.flatMap((g) =>
          g.keys.map((k) => ({
            id: `factor:${g.id}:${k}`,
            label: `${g.name(k)} factor (its own)`,
            type: 'number' as const,
            hint: `${factors.factors[g.id][k]} (the studio's)`,
          })),
        ),
        ...modelFields(w),
      ],
      values: {
        ...w,
        ...Object.fromEntries(
          (w.models || []).flatMap((m) =>
            m.resolutions.map((r) => [`model:${m.model}:${r}`, w.model_prices?.[m.model]?.[r]]),
          ),
        ),
        ...Object.fromEntries(
          GROUPS.flatMap((g) => g.keys.map((k) => [`factor:${g.id}:${k}`, (w.own_factors?.[g.id] || {})[k]])),
        ),
      },
      save: async (values) => {
        const mine = Object.fromEntries(
          GROUPS.map((g) => [
            g.id,
            Object.fromEntries(g.keys.map((k) => [k, values[`factor:${g.id}:${k}`]]).filter(([, v]) => v != null)),
          ]),
        );
        const plain = Object.fromEntries(
          Object.entries(values).filter(([k]) => !k.startsWith('factor:') && !k.startsWith('model:')),
        );
        await api('/api/admin/pricing/workflow', { method: 'PUT', json: { workflow: w.id, ...plain } });
        if (!w.id.startsWith('edit/'))
          await api('/api/admin/pricing/workflow/factors', { method: 'PUT', json: { workflow: w.id, ...mine } });
        if (w.models?.length) {
          const prices: Record<string, Record<string, number>> = {};
          for (const m of w.models)
            for (const r of m.resolutions) {
              const v = values[`model:${m.model}:${r}`];
              if (v != null) (prices[m.model] ??= {})[r] = Number(v);
            }
          await api('/api/admin/pricing/models', { method: 'PUT', json: { workflow: w.id, prices } });
        }
        await refresh();
      },
    });
  return (
    <div className={css('card')}>
      <div className={css('card-head')}>
        <h2>Workflows</h2>
      </div>
      <Table
        head={[
          'Workflow',
          'Type',
          'Rate',
          'Multiplier',
          'One image, or 5 seconds at 720p Final',
          'Preferred server',
          'Status',
        ]}
        rows={data.workflows.map((w) => [
          <div key="t">
            {w.title}
            <div className="muted small">{w.id}</div>
          </div>,
          w.kind,
          <div key="r">
            {rateText(w)}
            <div className="muted small">{own(w) ? 'Its own rate' : 'The rate of its type'}</div>
          </div>,
          <div key="m">
            {w.multiplier === 1 ? '' : '× ' + trim(w.multiplier)}
            {Object.values(w.own_factors || {}).some((g) => Object.keys(g).length) && (
              <div className="muted small">Its own factors</div>
            )}
          </div>,
          `${number(w.example)} credits · ${worth(w.example)}`,
          w.preferred_server || (
            <span key="s" className="muted">
              Any
            </span>
          ),
          <span key="p" className={css('pill ' + (!w.enabled ? 'cancelled' : w.admins_only ? 'running' : 'done'))}>
            {!w.enabled ? 'Switched off' : w.admins_only ? 'Admins only' : 'Offered'}
          </span>,
        ])}
        onRow={(i) => open(data.workflows[i])}
      />
      <p className="muted small" style={{ marginTop: 10 }}>
        Select a workflow to give it its own rate or multipliers, or to switch it off. The server is recorded for the
        scheduler; jobs are not routed by it yet.
      </p>
    </div>
  );
}

export default function Pricing() {
  const [editing, setEditing] = useState<Editing | null>(null);
  const query = useSection('pricing', [], async () => {
    // The agent models' prices come from a call of their own: when it fails, the rest of the section still shows.
    const [data, llm, factors] = await Promise.all([
      api<Data>('/api/admin/pricing'),
      api<Llm>('/api/admin/pricing/llm').catch((e: Error): Llm => ({ models: [], error: e.message, inr_per_usd: 0 })),
      api<Factors>('/api/admin/pricing/factors'),
    ]);
    return { data, llm, factors };
  });
  return (
    <Loaded query={query}>
      {({ data, llm, factors }) => {
        const version = JSON.stringify([data, factors]);
        return (
          <>
            <Rates key={'r' + version} data={data} />
            <FactorsCard key={'f' + version} data={data} factors={factors} />
            <Workflows data={data} factors={factors} edit={setEditing} />
            <LlmCard llm={llm} worth={(credits) => rupees((credits * data.inr_per_1000_credits) / 1000)} />
            <Packages data={data} edit={setEditing} />
            <Servers data={data} edit={setEditing} />
            {editing && <EditDialog key={editing.title} editing={editing} onClose={() => setEditing(null)} />}
          </>
        );
      }}
    </Loaded>
  );
}
