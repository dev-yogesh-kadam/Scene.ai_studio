// What the console's sections are built from: numbers in words, a person, a status, a table, a search box, and the
// parts of a drawer; and the questions (sure, say) in the studio's own window.

import { useEffect, useRef, useState, type ReactNode } from 'react';
import type { UseQueryResult } from '@tanstack/react-query';
import { ask } from '../../../common/components/Dialog';
import { Still } from '../../../common/components/Still';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared2.module.css';
import css1 from '../../../common/components/Shared3.module.css';
import css2 from '../../../common/components/Shared4.module.css';
import css3 from './Console.module.css';
import css4 from './ui.module.css';
const css = classesOf(css0, css1, css2, css3, css4);

export const STATUS: Record<string, string> = {
  queued: 'Waiting',
  running: 'Running',
  done: 'Done',
  failed: 'Failed',
  cancelled: 'Cancelled',
};

export const number = (value: number | null | undefined) => Number(value || 0).toLocaleString();
export const bytes = (value: number | null | undefined) => {
  const v = value || 0;
  if (v >= 1e9) return (v / 1e9).toFixed(1) + ' GB';
  if (v >= 1e6) return Math.round(v / 1e6) + ' MB';
  return Math.round(v / 1e3) + ' KB';
};
export const span = (seconds: number | null | undefined) => {
  if (seconds == null) return '';
  if (seconds < 90) return Math.round(seconds) + ' s';
  if (seconds < 5400) return (seconds / 60).toFixed(1).replace(/\.0$/, '') + ' min';
  return (seconds / 3600).toFixed(1) + ' h';
};
export const ago = (timestamp: number | null | undefined) => {
  if (!timestamp) return 'never';
  const seconds = Date.now() / 1000 - timestamp;
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return Math.round(seconds / 60) + ' min ago';
  if (seconds < 86400) return Math.round(seconds / 3600) + ' h ago';
  if (seconds < 86400 * 30) return Math.round(seconds / 86400) + ' d ago';
  return new Date(timestamp * 1000).toLocaleDateString([], { dateStyle: 'medium' });
};
/** How many seconds ago a moment was. */
export const secondsSince = (timestamp: number) => Date.now() / 1000 - timestamp;
export const stamp = (timestamp: number) =>
  new Date(timestamp * 1000).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });

/** A question in place of confirm(): its first sentence is the window's title, the rest its message. */
export function sure(text: string) {
  const cut = text.search(/[?.!](\s|$)/);
  const title = cut >= 0 ? text.slice(0, cut + 1) : text;
  return ask({ title, message: text.slice(title.length).trim() || undefined, confirm: 'OK' });
}
/** A notice with one button. */
export const say = (text: string) => ask({ title: text, confirm: 'OK', cancel: null });
export const failed = (e: unknown) => void say((e as Error).message);

export const Person = ({ name, email }: { name: ReactNode; email: ReactNode }) => (
  <div>
    {name}
    <div className="muted small">{email}</div>
  </div>
);
export const Pill = ({ status }: { status: string }) => (
  <span className={css('pill ' + status)}>{STATUS[status] || status}</span>
);
export const Tile = ({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) => (
  <div className={css('tile')}>
    <div className={css('tile-label')}>{label}</div>
    <div className={css('tile-value')}>{value}</div>
    {sub ? <div className="muted small">{sub}</div> : null}
  </div>
);

/** rows: arrays of cells. `onRow(index)` makes rows clickable. */
export function Table({
  head,
  rows,
  onRow,
  empty = 'Nothing here yet.',
}: {
  head: ReactNode[];
  rows: ReactNode[][];
  onRow?: (index: number) => void;
  empty?: string;
}) {
  return (
    <div className={css('table-wrap')} tabIndex={0}>
      <table>
        <tbody>
          <tr>
            {head.map((h, i) => (
              <th key={i}>{h}</th>
            ))}
          </tr>
          {rows.length ? (
            rows.map((cells, r) => (
              <tr
                key={r}
                className={css(onRow ? 'clickable' : undefined)}
                tabIndex={onRow ? 0 : undefined}
                onClick={onRow ? () => onRow(r) : undefined}
                onKeyDown={
                  onRow
                    ? (e) => {
                        if (e.key === 'Enter') onRow(r);
                      }
                    : undefined
                }
              >
                {cells.map((c, i) => (
                  <td key={i}>{c}</td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={head.length} className="muted">
                {empty}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

/** A search box that calls back a moment after typing stops. */
export function SearchBox({
  placeholder,
  value,
  onChange,
}: {
  placeholder: string;
  value: string;
  onChange: (text: string) => void;
}) {
  const [text, setText] = useState(value);
  const [seen, setSeen] = useState(value);
  if (seen !== value) {
    setSeen(value);
    setText(value);
  }
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  return (
    <input
      type="text"
      className="search"
      placeholder={placeholder}
      value={text}
      onChange={(e) => {
        const typed = e.target.value;
        setText(typed);
        clearTimeout(timer.current);
        timer.current = setTimeout(() => onChange(typed), 250);
      }}
    />
  );
}

export const ExportLink = ({ name }: { name: string }) => (
  <a className="btn small" href={`/api/admin/export/${name}.csv`} download="">
    Export CSV
  </a>
);

export const Section = ({ title, children }: { title: string; children: ReactNode }) => (
  <div className={css('drawer-section')}>
    <h3>{title}</h3>
    {children}
  </div>
);

export function Facts({ pairs }: { pairs: (readonly [string, ReactNode] | null | undefined | false)[] }) {
  const shown = pairs.filter(
    (p): p is readonly [string, ReactNode] => !!p && p[1] != null && p[1] !== '' && p[1] !== false,
  );
  return (
    <dl className={css('facts')}>
      {shown.flatMap(([k, v]) => [<dt key={k + ':t'}>{k}</dt>, <dd key={k + ':d'}>{v}</dd>])}
    </dl>
  );
}

export const itemUrl = (id: number) => `/api/admin/library/${id}/file`;
export const Thumb = ({ item }: { item: { id: number; kind: string; name: string } }) => (
  <Still url={itemUrl(item.id)} kind={item.kind} name={item.name} />
);

/** What a section asked for, once it has come; why not, if it did not. */
export function Loaded<T>({ query, children }: { query: UseQueryResult<T>; children: (data: T) => ReactNode }) {
  if (query.error && (query.error as { status?: number }).status !== 401)
    return <p className="error">{query.error.message}</p>;
  return query.data === undefined ? null : children(query.data);
}

/** The line of a form that says how it went. */
export const Notice = ({ notice }: { notice: { text: string; ok: boolean } }) => (
  <p className={'notice' + (notice.text ? (notice.ok ? ' ok' : ' error') : '')}>{notice.text}</p>
);

/** Older and newer pages of a long list. */
export function Pager({
  total,
  offset,
  onOffset,
}: {
  total: number;
  offset: number;
  onOffset: (offset: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / 50));
  const page = Math.floor(offset / 50) + 1;
  if (pages <= 1) return null;
  return (
    <div className={css('toolbar')} style={{ marginTop: 12 }}>
      <button className="btn small" disabled={page === 1} onClick={() => onOffset(offset - 50)}>
        Newer
      </button>
      <span className="muted small">{`Page ${page} of ${pages}`}</span>
      <button className="btn small" disabled={page === pages} onClick={() => onOffset(offset + 50)}>
        Older
      </button>
    </div>
  );
}
