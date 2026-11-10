// What the studio's pages and the phone site reported (POST /api/client-errors): how fast pages are for the people
// using them (Web Vitals of the last seven days, a tenth of page views) and the newest errors, with who, where and on
// which build. An error opens with its stack.

import { tell } from '../../../common/components/Dialog';
import { Facts, Table, ago } from '../shared/ui';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../shared/Console.module.css';
import s from './ClientErrors.module.css';
const css = classesOf(css0, css1);

type Vital = { name: string; count: number; p75: number | null; good: number | null };
type Reported = {
  id: number;
  app: string;
  kind: string;
  message: string;
  stack: string;
  page: string;
  build: string;
  user_agent: string;
  created: number;
  email: string | null;
};
export type ClientErrors = { errors: Reported[]; vitals: Vital[] };

const ABOUT: Record<string, string> = {
  LCP: 'Largest content shown',
  INP: 'Answer to a click or key',
  CLS: 'Layout shift',
};
const shown = (v: Vital) =>
  v.p75 == null
    ? 'No visits measured yet'
    : `${v.name === 'CLS' ? v.p75.toFixed(3) : `${Math.round(v.p75)} ms`} for 3 visits in 4 · ${Math.round(
        (v.good ?? 0) * 100,
      )}% good · ${v.count} measured`;

export function ClientErrorsCard({ c }: { c: ClientErrors }) {
  return (
    <div className={css('card')}>
      <div className={css('card-head')}>
        <h2>In the browser</h2>
      </div>
      <Facts pairs={c.vitals.map((v) => [`${ABOUT[v.name] ?? v.name} (${v.name})`, shown(v)] as const)} />
      <Table
        head={['When', 'Who', 'Where', 'What']}
        rows={c.errors.map((e) => [
          ago(e.created),
          e.email ?? '',
          `${e.app === 'phone' ? 'Phone' : 'Studio'} ${e.page}`,
          <span key="m" className={s.message}>
            {(e.kind === 'rejection' ? 'Unhandled: ' : '') + e.message}
          </span>,
        ])}
        onRow={(i) => {
          const e = c.errors[i];
          void tell(
            e.message,
            <pre
              className={s.stack}
            >{`${e.stack || 'No stack.'}\n\nBuild ${e.build || 'unknown'} · ${e.user_agent}`}</pre>,
          );
        }}
        empty="No errors reported."
      />
    </div>
  );
}
