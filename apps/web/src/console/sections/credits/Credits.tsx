// The console's Credits section: what was given and spent, every change, and the windows to give or take credits.

import { useState } from 'react';
import { api } from '../../../common/api';
import { Segmented } from '../../../common/components/Segmented';
import { useConsole, useFilters, useSection } from '../shared/context';
import { ExportLink, Loaded, Person, SearchBox, Table, Tile, failed, number, stamp } from '../shared/ui';
import { CreditsDialog, EveryoneDialog } from './CreditsDialog';
import { REASON } from './reasons';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../shared/Console.module.css';
const css = classesOf(css0, css1, css2);

type Data = {
  summary: { held: number; charged: number; refunded: number; welcome: number; granted: number };
  events: {
    created: number;
    user_name: string;
    user_email: string;
    amount: number;
    reason: string;
    job_name?: string;
    note?: string;
  }[];
};
type Person_ = { id: number; name: string; email: string; credits: number };

export default function Credits() {
  const { refresh } = useConsole();
  const [s, set] = useFilters<{ reason: string; q: string }>('credits');
  const [everyone, setEveryone] = useState(false);
  const [people, setPeople] = useState<Person_[] | null>(null);
  const query = useSection('credits', [s.reason, s.q], () =>
    api<Data>('/api/admin/credits?' + new URLSearchParams({ reason: s.reason, q: s.q })),
  );
  return (
    <Loaded query={query}>
      {({ summary: sum, events }) => (
        <>
          <div className={css('tiles')}>
            <Tile label="Held by users now" value={number(sum.held)} sub="what could still be spent" />
            <Tile
              label="Spent on generations"
              value={number(sum.charged - sum.refunded)}
              sub={`${number(sum.charged)} charged · ${number(sum.refunded)} refunded`}
            />
            <Tile label="Given at sign-up" value={number(sum.welcome)} />
            <Tile label="Given by admins" value={number(sum.granted)} sub="grants minus removals" />
          </div>
          <div className={css('toolbar')}>
            <Segmented
              choices={[
                { id: '', label: 'All' },
                { id: 'generation', label: 'Charges' },
                { id: 'refund', label: 'Refunds' },
                { id: 'admin grant', label: 'By admins' },
                { id: 'welcome', label: 'Sign-up' },
              ]}
              current={s.reason}
              onPick={(reason) => set({ reason })}
            />
            <SearchBox placeholder="Search user" value={s.q} onChange={(q) => set({ q })} />
            <span className={css('push')} />
            <ExportLink name="credits" />
            <button className="btn small" onClick={() => setEveryone(true)}>
              Give everyone credits
            </button>
            <button
              className="btn small primary"
              onClick={() =>
                void api<{ users: Person_[] }>('/api/admin/users').then((found) => setPeople(found.users), failed)
              }
            >
              Give or take credits
            </button>
          </div>
          <div className={css('card')}>
            <Table
              head={['When', 'User', 'Credits', 'Reason', 'Job or note']}
              rows={events.map((e) => [
                stamp(e.created),
                <Person key="p" name={e.user_name} email={e.user_email} />,
                <b key="b">{(e.amount > 0 ? '+' : '') + number(e.amount)}</b>,
                REASON[e.reason] || e.reason,
                e.job_name || e.note || '',
              ])}
              empty="No credit changes match."
            />
          </div>
          <p className="muted small" style={{ marginTop: 10 }}>
            The latest 300 changes. Export CSV gives the full history.
          </p>
          {everyone && (
            <EveryoneDialog
              onClose={() => setEveryone(false)}
              after={() => {
                setEveryone(false);
                void refresh();
              }}
            />
          )}
          {people && (
            <CreditsDialog
              people={people}
              onClose={() => setPeople(null)}
              after={() => {
                setPeople(null);
                void refresh();
              }}
            />
          )}
        </>
      )}
    </Loaded>
  );
}
