// The console's Economics section: what each workflow earned in credits and what it cost to run, from real jobs. The
// cost is electricity only. It is for the studio's own eyes: none of it is shown to users.

import { api } from '../../../common/api';
import { Segmented } from '../../../common/components/Segmented';
import { useConsole, useSection } from '../shared/context';
import { ExportLink, Loaded, Table, Tile, bytes, number, span } from '../shared/ui';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../shared/Console.module.css';
import css3 from '../../../studio/pages/create/CreatePage.module.css';
const css = classesOf(css0, css1, css2, css3);

const rupees = (value: number | null | undefined) =>
  value == null ? 'Not measured' : (value < 0 ? '−₹' : '₹') + Number(Math.abs(value).toFixed(2)).toLocaleString();
const percent = (value: number | null | undefined) => (value == null ? '' : value + '%');

type Workflow = {
  id: string;
  title: string;
  done: number;
  failed: number;
  success_rate: number;
  runs_per_success: number | null;
  avg_seconds: number;
  render_ratio: number | null;
  credits: number;
  revenue_inr: number;
  electricity_inr: number | null;
  margin_inr: number | null;
  output_bytes: number;
};
type Data = {
  days: number;
  electricity_inr_per_kwh: number;
  totals: {
    revenue_inr: number;
    credits: number;
    refunded: number;
    electricity_inr: number;
    run_seconds: number;
    margin_inr: number;
    margin_percent: number | null;
    failure_rate: number | null;
    failed: number;
    done: number;
    cancelled: number;
  };
  workflows: Workflow[];
  unmeasured: string[];
};

const None = () => <span className="muted">Not measured</span>;

export default function Economics() {
  const { days, setDays } = useConsole();
  const query = useSection('economics', [days], () => api<Data>('/api/admin/economics?days=' + days));
  return (
    <Loaded query={query}>
      {(data) => {
        const t = data.totals;
        return (
          <>
            <div className={css('toolbar')}>
              <Segmented
                choices={[7, 30, 90].map((d) => ({ id: d, label: `${d} days` }))}
                current={data.days}
                onPick={setDays}
              />
              <span className={css('push')} />
              <ExportLink name="jobs" />
            </div>
            <div className={css('tiles')}>
              <Tile
                label="Value of credits used"
                value={rupees(t.revenue_inr)}
                sub={`${number(t.credits)} credits used · ${number(t.refunded)} credits refunded`}
              />
              <Tile
                label="Electricity"
                value={rupees(t.electricity_inr)}
                sub={`${span(t.run_seconds) || '0 s'} of rendering at ₹${data.electricity_inr_per_kwh} per kWh`}
              />
              <Tile
                label="Left after electricity"
                value={rupees(t.margin_inr)}
                sub={t.margin_percent == null ? 'No credits used yet' : `${t.margin_percent}% of the value`}
              />
              <Tile
                label="Runs that failed"
                value={t.failure_rate == null ? 'None yet' : t.failure_rate + '%'}
                sub={`${number(t.failed)} failed · ${number(t.done)} done · ${number(t.cancelled)} cancelled`}
              />
            </div>
            <div className={css('card')}>
              <div className={css('card-head')}>
                <h2>By workflow</h2>
              </div>
              <Table
                head={[
                  'Workflow',
                  'Done',
                  'Failed',
                  'Runs per result',
                  'Avg. render',
                  'Render per second made',
                  'Credits used',
                  'Value',
                  'Electricity',
                  'Left',
                  'Output',
                ]}
                rows={data.workflows.map((w) => [
                  <div key="w">
                    {w.title}
                    <div className="muted small">{w.id}</div>
                  </div>,
                  number(w.done),
                  w.failed ? (
                    <span key="f" className="error">
                      {`${number(w.failed)} · ${percent(100 - w.success_rate)}`}
                    </span>
                  ) : (
                    '0'
                  ),
                  w.runs_per_success == null ? '' : String(w.runs_per_success),
                  span(w.avg_seconds),
                  w.render_ratio == null ? '' : span(w.render_ratio),
                  number(w.credits),
                  rupees(w.revenue_inr),
                  w.electricity_inr == null ? <None key="e" /> : rupees(w.electricity_inr),
                  w.margin_inr == null ? <None key="m" /> : <b key="m">{rupees(w.margin_inr)}</b>,
                  w.output_bytes ? bytes(w.output_bytes) : '',
                ])}
                empty="No jobs finished in this period."
              />
            </div>
            <p className="muted small" style={{ marginTop: 10 }}>
              Value is credits used at the price of 1,000 credits; until credits are sold it is what the work would have
              earned. Electricity is the time each job ran, failed runs included, at the power of its server. Cooling,
              depreciation, storage and bandwidth are not counted. Runs per result: 1.08 means 108 runs were needed for
              100 results. Jobs from before 5 October were priced by GPU time.
            </p>
            {data.unmeasured.length > 0 && (
              <p className="muted small">{`No power is set for ${data.unmeasured.join(' and ')}, so work done there shows as not measured. Set it in Pricing, under Servers.`}</p>
            )}
          </>
        );
      }}
    </Loaded>
  );
}
