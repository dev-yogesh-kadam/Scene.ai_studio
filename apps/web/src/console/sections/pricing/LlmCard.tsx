// What a message to the agent costs with each model.

import { useState } from 'react';
import { api } from '../../../common/api';
import { useConsole } from '../shared/context';
import { Table } from '../shared/ui';
import { rupees } from './pricingData';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../shared/Console.module.css';
import css3 from '../../../studio/pages/create/CreatePage.module.css';
const css = classesOf(css0, css1, css2, css3);

type Row = {
  model: string;
  credits: number;
  available: boolean;
  tokens?: { input: number; output: number; cache_read: number; cache_write: number };
};
export type Llm = { models: Row[]; inr_per_usd: number; error?: string };

export function LlmCard({ llm, worth }: { llm: Llm; worth: (credits: number) => string }) {
  const { refresh } = useConsole();
  const [error, setError] = useState('');
  const perMillion = (usd: number) => rupees(usd * llm.inr_per_usd);
  const save = (model: string, credits: string) =>
    api('/api/admin/pricing/llm', { method: 'PUT', json: { model, credits } }).then(refresh, (e: Error) =>
      setError(e.message),
    );
  return (
    <div className={css('card')}>
      <div className={css('card-head')}>
        <h2>Agent models</h2>
      </div>
      <p className="muted small">
        Credits taken for each message to the agent, by the model that answers it. 0 is free, except for Claude&apos;s
        models, which are charged by the tokens each answer uses unless they are given a price here. Captions, notes and
        the agent checking a result stay free.
      </p>
      <Table
        head={['Model', 'Credits per message', 'Worth', 'Status']}
        rows={llm.models.map((m) => [
          <b key="m">{m.model}</b>,
          <input
            key={'c' + m.credits}
            type="number"
            min={0}
            step={1}
            defaultValue={m.credits}
            style={{ width: 110 }}
            aria-label={`Credits per message for ${m.model}`}
            onBlur={(e) => e.target.value !== String(m.credits) && void save(m.model, e.target.value)}
          />,
          m.credits ? (
            worth(m.credits)
          ) : m.tokens ? (
            <span
              key="t"
              className="small"
              title={`$${m.tokens.input} in · $${m.tokens.output} out · $${m.tokens.cache_read} cache read · $${m.tokens.cache_write} cache write, per million tokens`}
            >
              {`By tokens: ${perMillion(m.tokens.input)} in, ${perMillion(m.tokens.output)} out, ${perMillion(m.tokens.cache_read)} cache read, ${perMillion(m.tokens.cache_write)} cache write per million`}
            </span>
          ) : (
            <span key="f" className="muted">
              Free
            </span>
          ),
          <span key="s" className={css('pill ' + (m.available ? 'done' : 'cancelled'))}>
            {m.available ? 'Available' : 'Not there now'}
          </span>,
        ])}
        empty={
          llm.error
            ? 'The prices of agent models could not be loaded. Restart the studio app, then open this tab again.'
            : 'No agent models are reachable now.'
        }
      />
      <p className={'notice' + (error ? ' error' : '')}>{error}</p>
    </div>
  );
}
