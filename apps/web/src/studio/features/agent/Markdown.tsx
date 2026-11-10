// A reply as paragraphs, lists, ```csv tables and other fenced blocks, with small pictures of the items it names.
// Nothing the model wrote is ever put in the page as HTML: every word is a React text child.

import { Fragment, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { Icon } from '../../../common/components/Icon/Icon';
import { Still } from '../../../common/components/Still';
import { useRetryOnce } from '../../../common/components/retryOnce';
import { cx } from '../../../common/cx';
import { SoundPlayer } from './SoundPlayer';
import type { Chip as Known, Chips } from './types';
import s from './Markdown.module.css';

export type OnPick = (table: string, id: number) => void;

const fileUrl = (table: string, id: number) => (table === 'item' ? `/api/library/${id}/file` : `/api/kit/${id}/file`);

/** An item or a saved asset named in a message: its picture and its name; while the pointer rests on it, a bigger look. */
export function Chip({ table, id, known, onPick }: { table: string; id: number; known: Known; onPick: OnPick }) {
  const node = useRef<HTMLButtonElement>(null);
  const [shown, setShown] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const looks = known.kind === 'image' || known.kind === 'video';
  const hide = () => {
    clearTimeout(timer.current);
    setShown(false);
  };
  return (
    <>
      <button
        ref={node}
        type="button"
        className={s['md-chip']}
        title={known.name}
        onClick={() => {
          hide();
          onPick(table, id);
        }}
        onPointerEnter={(e) => {
          if (!looks || e.pointerType === 'touch') return;
          timer.current = setTimeout(() => setShown(true), 180); // passing over a chip does not open it
        }}
        onPointerLeave={hide}
      >
        <span className={s['md-chip-thumb']}>
          <Still url={fileUrl(table, id)} kind={known.kind} name={known.name} />
        </span>
        <span className={s['md-chip-name']}>{known.name}</span>
      </button>
      {shown && <ChipPreview anchor={node} table={table} id={id} known={known} onGone={hide} />}
    </>
  );
}

function ChipPreview({
  anchor,
  table,
  id,
  known,
  onGone,
}: {
  anchor: RefObject<HTMLButtonElement | null>;
  table: string;
  id: number;
  known: Known;
  onGone: () => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const place = () => {
    const node = box.current;
    const r = anchor.current?.getBoundingClientRect();
    if (!node || !r) return;
    const w = node.offsetWidth;
    const h = node.offsetHeight;
    node.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, r.left + r.width / 2 - w / 2)) + 'px';
    node.style.top = (r.top - h - 8 >= 8 ? r.top - h - 8 : Math.min(window.innerHeight - h - 8, r.bottom + 8)) + 'px';
  };
  useLayoutEffect(place);
  useLayoutEffect(() => {
    window.addEventListener('scroll', onGone, true);
    return () => window.removeEventListener('scroll', onGone, true);
  }, [onGone]);
  const url = fileUrl(table, id);
  return createPortal(
    <div ref={box} className={s['chip-preview']} role="tooltip">
      {known.kind === 'video' ? (
        <video
          src={url}
          poster={table === 'item' ? `/api/library/${id}/poster` : undefined}
          muted
          autoPlay
          loop
          playsInline
          preload="auto"
          onLoadedMetadata={place}
        />
      ) : (
        <img src={url} alt={known.name} decoding="async" onLoad={place} />
      )}
    </div>,
    document.body,
  );
}

/** A file the reply hands over ([[show:item:12]] on a line of its own): the file itself, its name, Download, Copy link
 *  (the studio's own link: it opens only for someone signed in who may see it) and Open. */
function MediaCard({ table, id, known, onPick }: { table: string; id: number; known: Known; onPick: OnPick }) {
  const [copy, setCopy] = useState('Copy link');
  const url = fileUrl(table, id);
  const view =
    known.kind === 'video' ? (
      <video
        src={url}
        controls
        preload="metadata"
        playsInline
        poster={table === 'item' ? `/api/library/${id}/poster` : undefined}
      />
    ) : known.kind === 'image' ? (
      <img src={url} alt={known.name} loading="lazy" />
    ) : known.kind === 'audio' ? (
      <SoundPlayer url={url} name={known.name} />
    ) : null;
  return (
    <figure className={cx(s['md-media'], s[`md-media-${known.kind}`])}>
      {view && <div className={s['md-media-view']}>{view}</div>}
      <figcaption>
        <span className={s['md-media-name']} title={known.name}>
          {known.name}
        </span>
        <a
          className={s['md-media-act']}
          href={table === 'item' ? `/api/library/${id}/file?download=1` : url}
          download={table === 'item' ? undefined : known.name}
          title="Download"
        >
          <Icon name="download" />
          Download
        </a>
        <button
          type="button"
          className={s['md-media-act']}
          title="Copy link"
          onClick={() => {
            navigator.clipboard.writeText(new URL(known.link || url, location.origin).href).then(
              () => setCopy('Copied'),
              () => setCopy('Could not copy'),
            );
            setTimeout(() => setCopy('Copy link'), 1600);
          }}
        >
          <Icon name="copy" />
          {copy}
        </button>
        <button
          type="button"
          className={s['md-media-act']}
          title="Open in the studio"
          onClick={() => onPick(table, id)}
        >
          <Icon name="expand" />
          Open
        </button>
      </figcaption>
    </figure>
  );
}

const SHOW_LINE = /^\s*\[\[show:(item|asset):(\d+)\]\]\s*$/;
const LIST = /^\s*([-*•]|\d+[.)])\s+/;
const FENCE = /```([\w-]*)[ \t]*\n([\s\S]*?)\n```/g; // ```csv is a table, any other a block of text to copy
const LIBRARY_LINK = /^\/api\/(library|assets)\/(\d+)\/file$/;
const TOKEN = /\[\[(?:show:)?(item|asset):(\d+)\]\]/g;

/** One line of a reply: **bold**, *italic*, `code` and [[item:12]] / [[asset:3]]. */
function inline(text: string, chips: Chips, onPick: OnPick): ReactNode[] {
  const parts: ReactNode[] = [];
  const pattern =
    /\[\[(?:show:)?(item|asset):(\d+)\]\]|\*\*([^*]+)\*\*|`([^`]+)`|(?<![\w*])\*([^*\s][^*]*?)\*(?![\w*])/g;
  let last = 0;
  let found;
  while ((found = pattern.exec(text))) {
    if (found.index > last) parts.push(text.slice(last, found.index));
    if (found[1]) {
      const known = chips[`${found[1]}:${found[2]}`];
      if (known)
        parts.push(<Chip key={found.index} table={found[1]} id={Number(found[2])} known={known} onPick={onPick} />);
    } else if (found[3]) parts.push(<b key={found.index}>{found[3]}</b>);
    else if (found[4]) parts.push(<code key={found.index}>{found[4]}</code>);
    else if (found[5]) parts.push(<i key={found.index}>{found[5]}</i>);
    last = pattern.lastIndex;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

/** One row of CSV: commas split cells, a cell in double quotes may hold commas ("" is a quote mark). */
function csvRow(line: string) {
  const cells: string[] = [];
  let cell = '';
  let quoted = false;
  for (let i = 0; i < line.length; i += 1) {
    const c = line[i];
    if (quoted && c === '"' && line[i + 1] === '"') {
      cell += '"';
      i += 1;
    } else if (c === '"') quoted = !quoted;
    else if (c === ',' && !quoted) {
      cells.push(cell.trim());
      cell = '';
    } else cell += c;
  }
  cells.push(cell.trim());
  return cells;
}

/** A link to one of the user's library items shows its picture (a video its poster, found when the file is not one). */
function MediaCell({ text, found }: { text: string; found: RegExpExecArray }) {
  const [tried, setTried] = useState<'file' | 'poster' | 'none'>('file');
  // the poster may not be made yet (503): once more a second later, then the word "open"
  const poster = useRetryOnce(`/api/library/${found[2]}/poster`, () => setTried('none'));
  return (
    <td className={s['md-cell-media']}>
      <a href={text} target="_blank" rel="noopener noreferrer" title={tried === 'none' ? undefined : text}>
        {tried === 'none' ? (
          'open'
        ) : (
          <img
            src={tried === 'poster' ? poster.src : text}
            alt=""
            loading="lazy"
            onError={
              tried === 'poster'
                ? poster.onError
                : () => setTried(found[1] === 'library' && tried === 'file' ? 'poster' : 'none')
            }
          />
        )}
      </a>
    </td>
  );
}

function CopyButton({ text, title, label }: { text: () => string; title: string; label: string }) {
  const [hint, setHint] = useState(title);
  return (
    <button
      type="button"
      className={cx('icon-btn small', hint !== title && s.done)}
      title={hint}
      aria-label={label}
      onClick={() => {
        navigator.clipboard.writeText(text()).then(
          () => {
            setHint('Copied');
            setTimeout(() => setHint(title), 1500);
          },
          () => {},
        );
      }}
    >
      <Icon name="copy" />
    </button>
  );
}

/** A table in a box of its own that scrolls inside the reply, with Copy (the CSV) and Download (a .csv file). */
function Table({ csv, chips, onPick }: { csv: string; chips: Chips; onPick: OnPick }) {
  const link = useRef<HTMLAnchorElement>(null);
  const [head, ...rows] = csv
    .split('\n')
    .filter((line) => line.trim())
    .map(csvRow);
  // each [[item:12]] becomes the whole link to its file, the studio's own when the reply gave one
  const text = () =>
    csv
      .trim()
      .replace(
        TOKEN,
        (_, kind: string, id: string) =>
          new URL(chips[`${kind}:${id}`]?.link || fileUrl(kind, Number(id)), location.origin).href,
      );
  return (
    <div className={s['md-table-box']}>
      <div className={s['md-table-tools']}>
        <CopyButton text={text} title="Copy the table" label="Copy the table" />
        <button
          type="button"
          className="icon-btn small"
          title="Download as CSV"
          aria-label="Download the table as CSV"
          onClick={() => {
            if (!link.current) return;
            const url = URL.createObjectURL(new Blob([text() + '\n'], { type: 'text/csv' }));
            link.current.href = url;
            link.current.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
          }}
        >
          <Icon name="download" />
        </button>
        <a ref={link} download="table.csv" hidden />
      </div>
      <div className={s['md-table']}>
        <table>
          <thead>
            <tr>
              {(head || []).map((h, i) => (
                <th key={i}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((cells, r) => (
              <tr key={r}>
                {cells.map((cell, c) => {
                  const found = LIBRARY_LINK.exec(cell);
                  return found ? (
                    <MediaCell key={c} text={cell} found={found} />
                  ) : (
                    <td key={c}>{cell.includes('[[') ? inline(cell, chips, onPick) : cell}</td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function prose(text: string, chips: Chips, onPick: OnPick, at: number) {
  const out: ReactNode[] = [];
  let n = 0;
  const key = () => `${at}:${n++}`;
  for (const block of text.split(/\n{2,}/)) {
    let list: { ordered: boolean; items: ReactNode[] } | null = null;
    let paragraph: ReactNode[] | null = null;
    for (const line of block.split('\n')) {
      const shown = SHOW_LINE.exec(line);
      if (shown) {
        const known = chips[`${shown[1]}:${shown[2]}`];
        if (known) {
          list = null;
          paragraph = null;
          // the key is the file's: a video playing goes on playing when the conversation is drawn again
          out.push(
            <MediaCard
              key={`${shown[1]}:${shown[2]}:${n++}`}
              table={shown[1]}
              id={Number(shown[2])}
              known={known}
              onPick={onPick}
            />,
          );
        }
      } else if (LIST.test(line)) {
        paragraph = null;
        const ordered = /^\s*\d/.test(line);
        if (!list || list.ordered !== ordered) {
          const items: ReactNode[] = [];
          list = { ordered, items };
          const k = key();
          out.push(ordered ? <ol key={k}>{items}</ol> : <ul key={k}>{items}</ul>);
        }
        list.items.push(<li key={list.items.length}>{inline(line.replace(LIST, ''), chips, onPick)}</li>);
      } else if (line.trim()) {
        list = null;
        if (!paragraph) {
          paragraph = [];
          out.push(<p key={key()}>{paragraph}</p>);
        } else paragraph.push(<br key={paragraph.length} />);
        const from = paragraph.length;
        paragraph.push(
          ...inline(line, chips, onPick).map((part, i) => <Fragment key={`${from}:${i}`}>{part}</Fragment>),
        );
      }
    }
  }
  return out;
}

export function Markdown({ text, chips = {}, onPick }: { text: string; chips?: Chips; onPick: OnPick }) {
  const out: ReactNode[] = [];
  const source = String(text || '').replace(/\r/g, '');
  let at = 0;
  for (const found of source.matchAll(FENCE)) {
    out.push(...prose(source.slice(at, found.index), chips, onPick, at));
    out.push(
      found[1].toLowerCase() === 'csv' ? (
        <Table key={'t' + found.index} csv={found[2]} chips={chips} onPick={onPick} />
      ) : (
        <div key={'t' + found.index} className={cx(s['md-table-box'], s['md-text-box'])}>
          <div className={s['md-table-tools']}>
            <CopyButton text={() => found[2]} title="Copy the text" label="Copy the text" />
          </div>
          <pre className={s['md-text']}>{found[2]}</pre>
        </div>
      ),
    );
    at = found.index + found[0].length;
  }
  return [...out, ...prose(source.slice(at), chips, onPick, at)];
}
