// What the resolution and quality a person picks multiply the price by, and what that comes to.

import { useState } from 'react';
import { api } from '../../../common/api';
import { useConsole, useNotice } from '../shared/context';
import { Notice, Table, number } from '../shared/ui';
import { GROUPS, type Data, type Factors } from './pricingData';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared.module.css';
import css1 from '../../../common/components/Shared2.module.css';
import css2 from '../../../common/components/Shared3.module.css';
import css3 from '../../../studio/pages/create/CreatePage.module.css';
const css = classesOf(css0, css1, css2, css3);

type Boxes = Record<string, Record<string, string>>;

export function FactorsCard({ data, factors }: { data: Data; factors: Factors }) {
  const { refresh } = useConsole();
  const [boxes, setBoxes] = useState<Boxes>(() =>
    Object.fromEntries(
      GROUPS.map((g) => [g.id, Object.fromEntries(g.keys.map((k) => [k, String(factors.factors[g.id][k])]))]),
    ),
  );
  const { notice, run } = useNotice();
  const f = (g: string, k: string) => Number(boxes[g][k] || 0);
  const video = (r: string, q: string) => Math.ceil(data.rates.video * 5 * f('resolution', r) * f('quality', q));
  const fill = (from: (g: string, k: string) => number | undefined) =>
    setBoxes((was) =>
      Object.fromEntries(
        GROUPS.map((g) => [
          g.id,
          Object.fromEntries(g.keys.map((k) => [k, from(g.id, k) != null ? String(from(g.id, k)) : was[g.id][k]])),
        ]),
      ),
    );
  return (
    <div className={css('card')}>
      <div className={css('card-head')}>
        <h2>Quality and size</h2>
      </div>
      <p className="muted small">
        What the resolution and quality a person picks multiply the price by. 1 is the rate itself. Each choice in the
        studio shows its price before anything runs.
      </p>
      <div className={css('grid2')}>
        {GROUPS.map((g) => (
          <div key={g.id}>
            <h3>{g.label}</h3>
            <p className="muted small">{g.about}</p>
            <Table
              head={['', 'Factor', 'From render times']}
              rows={g.keys.map((k) => {
                const suggested = factors.suggested[g.id]?.[k];
                const jobs = factors.samples[g.id]?.[k];
                return [
                  g.name(k),
                  <input
                    key="i"
                    type="number"
                    min={0}
                    max={20}
                    step={0.05}
                    value={boxes[g.id][k]}
                    style={{ width: 90 }}
                    aria-label={`${g.label} ${g.name(k)} factor`}
                    onChange={(e) => setBoxes((was) => ({ ...was, [g.id]: { ...was[g.id], [k]: e.target.value } }))}
                  />,
                  suggested != null ? (
                    `× ${suggested} (${jobs} job${jobs === 1 ? '' : 's'})`
                  ) : (
                    <span key="n" className="muted">
                      No renders yet
                    </span>
                  ),
                ];
              })}
            />
          </div>
        ))}
      </div>
      <h3>What that comes to</h3>
      <div>
        <Table
          head={['5 s of video', 'Draft', 'Final']}
          rows={GROUPS[0].keys.map((r) => [
            r + 'p',
            number(video(r, 'draft')) + ' cr',
            number(video(r, 'final')) + ' cr',
          ])}
        />
        <p className="muted small" style={{ marginTop: 6 }}>
          {`A picture: ${number(Math.ceil(data.rates.image * f('quality', 'draft')))} cr on Draft, ${number(Math.ceil(data.rates.image * f('quality', 'final')))} cr on Final.`}
        </p>
      </div>
      <Notice notice={notice} />
      <div className="row" style={{ marginTop: 12 }}>
        <button
          className="btn primary"
          onClick={() =>
            void run(async () => {
              await api('/api/admin/pricing/factors', { method: 'PUT', json: boxes });
              await refresh();
            })
          }
        >
          Save
        </button>
        <button
          className="btn"
          disabled={!Object.keys(factors.suggested).length}
          title="Put in the factors worked out from how long each kind of render took"
          onClick={() => fill((g, k) => factors.suggested[g]?.[k])}
        >
          Use suggested
        </button>
        <button className="btn quiet" onClick={() => fill((g, k) => factors.defaults[g][k])}>
          Start values
        </button>
      </div>
    </div>
  );
}
