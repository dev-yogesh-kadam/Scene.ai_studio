// A small chart kit: column charts, a table of the same numbers, sparklines, bar lists and meters. Plain elements, no
// library. Colours come from the --series-* and --status-* tokens.

import { useState, type ReactNode } from 'react';
import { useHoldWhileUsed } from '../busy';
import { classesOf } from '../cx';
import css0 from './Charts.module.css';
import css1 from './Shared2.module.css';
import css2 from './Shared3.module.css';
import css3 from './Shared4.module.css';
import css4 from '../../console/sections/overview/Cards.module.css';
import css5 from '../../studio/pages/create/CreatePage.module.css';
const css = classesOf(css0, css1, css2, css3, css4, css5);

export type Series = { name: string; color: string; values: number[] };
export type ChartSpec = { labels: string[]; series: Series[]; format?: (n: number) => string; height?: number };

function niceMax(value: number) {
  if (value <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  return [1, 2, 5, 10].map((m) => m * power).find((m) => m >= value) ?? value;
}

const Swatch = ({ color }: { color: string }) => <span className={css('swatch')} style={{ background: color }} />;

/** A column per label, stacked when there are several series. Hover or focus a column for its values. */
export function ColumnChart({ labels, series, format = String, height = 170 }: ChartSpec) {
  const totals = labels.map((_, i) => series.reduce((sum, s) => sum + s.values[i], 0));
  const max = niceMax(Math.max(...totals));
  const [tip, setTip] = useState<{ i: number; left: number } | null>(null);
  const hold = useHoldWhileUsed();
  // Label a handful of columns so the axis stays readable at 90 days.
  const every = Math.ceil(labels.length / 6);
  const short = (label: string) => label.slice(5);
  const show = (i: number, column: HTMLElement) => {
    const left = column.offsetLeft + column.offsetWidth / 2;
    setTip({ i, left: Math.min(Math.max(left, 80), (column.parentElement?.offsetWidth ?? 0) - 80) });
  };
  return (
    <div className={css('chart')} {...hold}>
      {series.length > 1 && (
        <div className={css('legend')}>
          {series.map((s) => (
            <span key={s.name}>
              <Swatch color={s.color} />
              {s.name}
            </span>
          ))}
        </div>
      )}
      <div className={css('plot')} style={{ height }}>
        {[1, 0.5, 0].map((t) => (
          <div key={t} className={css('grid-line')} style={{ bottom: `${t * 100}%` }}>
            <span>{format(max * t)}</span>
          </div>
        ))}
        <div className={css('cols')} onPointerLeave={() => setTip(null)}>
          {labels.map((label, i) => (
            <div
              key={label + i}
              className={css('col')}
              role="img"
              tabIndex={0}
              aria-label={`${label}: ${format(totals[i])}`}
              onPointerEnter={(e) => show(i, e.currentTarget)}
              onFocus={(e) => show(i, e.currentTarget)}
              onBlur={() => setTip(null)}
            >
              {series
                .filter((s) => s.values[i] > 0)
                .map((s) => (
                  <div
                    key={s.name}
                    className={css('seg-bar')}
                    style={{ height: `${(100 * s.values[i]) / max}%`, background: s.color }}
                  />
                ))}
            </div>
          ))}
          <div className={css('chart-tip' + (tip ? '' : ' hidden'))} style={tip ? { left: tip.left } : undefined}>
            {tip && (
              <>
                <div className={css('tip-title')}>{labels[tip.i]}</div>
                {series.map((s) => (
                  <div key={s.name} className={css('tip-row')}>
                    <span className={css('tip-key')} style={{ background: s.color }} />
                    <b>{format(s.values[tip.i])}</b>
                    <span className="muted">{s.name}</span>
                  </div>
                ))}
                {series.length > 1 && (
                  <div className={css('tip-row')}>
                    <span className={css('tip-key')} />
                    <b>{format(totals[tip.i])}</b>
                    <span className="muted">Total</span>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
      <div className={css('x-axis')}>
        {labels.map((label, i) => (
          <span key={label + i}>{i % every === 0 || i === labels.length - 1 ? short(label) : ''}</span>
        ))}
      </div>
    </div>
  );
}

/** The same numbers as rows, for people who prefer a table (and for values the bars can't label). */
export function ChartTable({ labels, series, format = String }: ChartSpec) {
  return (
    <div className={css('table-wrap chart-table')} tabIndex={0}>
      <table>
        <tbody>
          <tr>
            <th>Day</th>
            {series.map((s) => (
              <th key={s.name}>{s.name}</th>
            ))}
          </tr>
          {labels
            .map((label, i) => (
              <tr key={label + i}>
                <td>{label}</td>
                {series.map((s) => (
                  <td key={s.name}>{format(s.values[i])}</td>
                ))}
              </tr>
            ))
            .reverse()}
        </tbody>
      </table>
    </div>
  );
}

/** A card holding a chart, with a Chart / Table switch. */
export function ChartCard({ title, subtitle, spec }: { title: ReactNode; subtitle: ReactNode; spec: ChartSpec }) {
  const [table, setTable] = useState(false);
  return (
    <div className={css('card')}>
      <div className={css('card-head')}>
        <div style={{ flex: 1 }}>
          <h2>{title}</h2>
          <div className="muted small">{subtitle}</div>
        </div>
        <button className="btn small quiet" onClick={() => setTable(!table)}>
          {table ? 'Show chart' : 'Show table'}
        </button>
      </div>
      <div>{table ? <ChartTable {...spec} /> : <ColumnChart {...spec} />}</div>
    </div>
  );
}

/** A tiny trend line for a stat tile. No axes: the tile's number is the value, this is the shape. */
export function Sparkline({ values }: { values: number[] }) {
  const max = Math.max(...values, 1);
  const step = values.length > 1 ? 100 / (values.length - 1) : 100;
  const points = values.map((v, i) => `${(i * step).toFixed(2)},${(28 - (26 * v) / max).toFixed(2)}`).join(' ');
  return (
    <svg viewBox="0 0 100 30" preserveAspectRatio="none" className={css('spark')} aria-hidden="true">
      <polyline points={points} />
    </svg>
  );
}

export type BarRow = { label: ReactNode; sub?: string; value: number; title?: string; key?: string | number };

/** Ranked horizontal bars: one hue, value at the end of each bar. */
export function BarList({ rows, format = String }: { rows: BarRow[]; format?: (n: number) => string }) {
  const max = Math.max(...rows.map((r) => r.value), 1);
  return (
    <div className={css('bar-list')}>
      {rows.map((r, i) => (
        <div key={r.key ?? i} className={css('bar-row')} title={r.title || ''}>
          <div className={css('bar-name')}>
            {r.label}
            {r.sub && <span className="muted small">{' ' + r.sub}</span>}
          </div>
          <div className={css('bar-track')}>
            <div className={css('bar-value')} style={{ width: `${Math.max(1.5, (100 * r.value) / max)}%` }} />
          </div>
          <div className={css('bar-number')}>{format(r.value)}</div>
        </div>
      ))}
    </div>
  );
}

/** A used / total meter with its numbers written out. */
export function Meter({
  label,
  used,
  total,
  format,
}: {
  label: string;
  used: number;
  total: number;
  format: (n: number) => string;
}) {
  const share = total ? Math.min(100, (100 * used) / total) : 0;
  return (
    <div className={css('meter')}>
      <div className={css('meter-head')}>
        <span>{label}</span>
        <span className="muted">{`${format(used)} of ${format(total)} used (${Math.round(share)}%)`}</span>
      </div>
      <div className={css('bar-track')}>
        <div className={css('bar-value' + (share > 90 ? ' high' : ''))} style={{ width: `${share}%` }} />
      </div>
    </div>
  );
}
