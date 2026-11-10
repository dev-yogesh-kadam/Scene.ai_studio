// The module's memory as a tree, in the manner of Frameo's: folders at the top (the cast, the assets, and the notes the
// agent and its skills keep), each with how many things it holds, how large it is and when it last changed; inside, a
// card for each thing (its name, the line under it, the names of the rest as chips) that opens on a grid of what it
// holds. A value that names a file shows its picture; a long text is cut short with "more". A note can be changed.

import { useState, type ReactNode } from 'react';
import type { AssetRecord, Memory, MemoryLeaf } from '@scene/shared/api/kit';
import { Icon } from '../../../common/components/Icon/Icon';
import { thumbUrl } from '../../../common/components/Still';
import { cx, mergeModules } from '../../../common/cx';
import { ago } from '../../../common/format';
import s1 from './Kit.module.css';
import s2 from './Kit2.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared3.module.css';

const s = mergeModules(s1, s2);
const css = classesOf(css0);

const LONG = 160; // characters of a value shown before "more"
const REF = /^\$state:\/assets\/([0-9a-f]{12})(?:\/url)?$/;

type Node = { kids: Map<string, Node>; leaf: MemoryLeaf | null };
type Value = Node | unknown;

/** The leaves of the module's notes as a tree. */
export function treeOf(leaves: MemoryLeaf[]): Node {
  const root: Node = { kids: new Map(), leaf: null };
  for (const leaf of leaves) {
    let at = root;
    for (const part of leaf.path.split('/').filter(Boolean)) {
      if (!at.kids.has(part)) at.kids.set(part, { kids: new Map(), leaf: null });
      at = at.kids.get(part)!;
    }
    at.leaf = leaf;
  }
  return root;
}

const isNode = (x: Value): x is Node => !!x && typeof x === 'object' && (x as Node).kids instanceof Map;
const isObject = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === 'object';
export const natural = (a: [string, unknown], b: [string, unknown]) =>
  a[0].localeCompare(b[0], undefined, { numeric: true });

/** What is inside a node of the tree or a value kept in a leaf, as [name, child] pairs; null for a plain value. */
export function partsOf(x: Value): [string, Value][] | null {
  if (isNode(x)) {
    if (x.kids.size) return [...x.kids.entries()].sort(natural);
    return x.leaf && isObject(x.leaf.value) ? partsOf(x.leaf.value) : null;
  }
  if (Array.isArray(x)) return x.map((v, i) => [String(i + 1), v]);
  return isObject(x) ? Object.entries(x) : null;
}
const valueOf = (x: Value) => (isNode(x) ? (x.leaf ? x.leaf.value : undefined) : x);
const plain = (x: Value) => partsOf(x) === null;
export const jsonOf = (x: Value): unknown =>
  isNode(x) ? (x.kids.size ? Object.fromEntries(partsOf(x)!.map(([k, v]) => [k, jsonOf(v)])) : x.leaf?.value) : x;
export const latest = (x: Value): number =>
  isNode(x) ? Math.max(x.leaf ? x.leaf.updated || 0 : 0, ...[...x.kids.values()].map(latest)) : 0;
export const kilobytes = (x: unknown) => `${(new Blob([JSON.stringify(x)]).size / 1024).toFixed(1)} KB`;
export { isNode };

/** What the tree's folders and cards share: which are open, the long values shown whole, the catalogue's records. */
export type TreeState = {
  open: Set<string>;
  toggle: (path: string) => void;
  long: Set<string>;
  more: (path: string) => void;
  known: Map<string, AssetRecord>;
  writable: boolean;
  edit: (leaf: MemoryLeaf) => void;
};

export function Thumb({ record }: { record: AssetRecord | undefined }) {
  const [broken, setBroken] = useState(false);
  if (!record) return null;
  if (record.kind !== 'image' && record.kind !== 'video')
    return (
      <span className={cx(s['mem-thumb'], s.glyph)}>
        <Icon name={record.kind === 'audio' ? 'audio' : 'book'} />
      </span>
    );
  const src = record.item ? `/api/library/${record.item}/poster` : thumbUrl(record.url ?? '');
  return (
    <span className={cx(s['mem-thumb'], record.kind === 'video' && s.video)}>
      {!broken && <img src={src} alt="" loading="lazy" onError={() => setBroken(true)} />}
      {record.kind === 'video' && <Icon name="play" />}
    </span>
  );
}

function Copy({ text, what }: { text: string; what: string }) {
  return (
    <button
      type="button"
      className={cx('icon-btn', s['mem-act'])}
      title={`Copy ${what}`}
      aria-label={`Copy ${what}`}
      onClick={(e) => {
        e.stopPropagation();
        navigator.clipboard?.writeText(text).catch(() => {});
      }}
    >
      <Icon name="copy" />
    </button>
  );
}

function Change({ leaf, path, tree }: { leaf: MemoryLeaf | null; path: string; tree: TreeState }) {
  if (!leaf || !tree.writable) return null;
  return (
    <button
      type="button"
      className={cx('icon-btn', s['mem-act'])}
      title="Change it"
      aria-label={`Change ${path}`}
      onClick={(e) => {
        e.stopPropagation();
        tree.edit(leaf);
      }}
    >
      <Icon name="pencil" />
    </button>
  );
}

/** One value as Frameo shows it: a number in colour, a reference to a file with its picture, a long text cut short. */
function ValueCell({ value, path, tree }: { value: unknown; path: string; tree: TreeState }) {
  if (typeof value === 'number' || typeof value === 'boolean' || value === null)
    return <span className={cx(s['mem-val'], s.num)}>{String(value)}</span>;
  const text = String(value);
  const ref = text.match(REF);
  if (ref)
    return (
      <span className={s['mem-val']}>
        <span>{text}</span>
        <Thumb record={tree.known.get(ref[1])} />
      </span>
    );
  if (text.length <= LONG || tree.long.has(path)) return <span className={s['mem-val']}>{text}</span>;
  return (
    <span className={s['mem-val']}>
      {text.slice(0, LONG).trimEnd() + '…'}
      <button type="button" className={s['mem-more']} onClick={() => tree.more(path)}>
        more
      </button>
    </span>
  );
}

function Chips({ names }: { names: string[] }) {
  if (!names.length) return null;
  const shown = names.slice(0, 4);
  return (
    <div className={s['mem-chips']}>
      {shown.join(' · ') + (names.length > shown.length ? ` · +${names.length - shown.length}` : '')}
    </div>
  );
}

/** A row of a card's grid: the name, then a plain value, a smaller grid (a group of plain values) or cards. */
export function GridRow({
  name,
  child,
  path,
  owner,
  tree,
}: {
  name: string;
  child: Value;
  path: string;
  owner: MemoryLeaf | null;
  tree: TreeState;
}) {
  const leaf = isNode(child) && child.leaf ? child.leaf : owner;
  const parts = partsOf(child);
  if (parts === null) {
    const value = valueOf(child);
    return (
      <div className={s['mem-row']}>
        <span className={s['mem-key']}>{name}</span>
        <ValueCell value={value} path={path} tree={tree} />
        <span className={s['mem-acts']}>
          <Copy text={typeof value === 'string' ? value : JSON.stringify(value)} what="the value" />
          <Change leaf={leaf} path={path} tree={tree} />
        </span>
      </div>
    );
  }
  const all = parts.every(([, v]) => plain(v));
  return (
    <div className={s['mem-row']}>
      <span className={s['mem-key']}>{name}</span>
      <div className={all ? s['mem-grid'] : s['mem-cards']}>
        {parts.map(([k, v]) =>
          all ? (
            <GridRow key={k} name={k} child={v} path={`${path}/${k}`} owner={leaf} tree={tree} />
          ) : (
            <Card key={k} name={k} child={v} path={`${path}/${k}`} owner={leaf} tree={tree} />
          ),
        )}
      </div>
    </div>
  );
}

/** A card: its name, the line under it and the chips of the rest; open, the grid of what it holds. */
export function Card({
  name,
  child,
  path,
  owner,
  tree,
}: {
  name: string;
  child: Value;
  path: string;
  owner: MemoryLeaf | null;
  tree: TreeState;
}) {
  const parts = partsOf(child);
  if (parts === null) return <GridRow name={name} child={child} path={path} owner={owner} tree={tree} />;
  const leaf = isNode(child) && child.leaf ? child.leaf : owner;
  const first = parts.findIndex(([, v]) => plain(v) && valueOf(v) !== undefined && valueOf(v) !== '');
  const line = first < 0 ? '' : String(valueOf(parts[first][1]));
  const rest = parts.filter((_, i) => i !== first).map(([k]) => k);
  const open = tree.open.has(path);
  const ref = line.match(REF);
  return (
    <div className={cx(s['mem-card'], open && s.open)}>
      <div className={s['mem-card-head']} onClick={() => tree.toggle(path)}>
        {ref ? <Thumb record={tree.known.get(ref[1])} /> : null}
        <div className={s['mem-card-text']}>
          <b>{name}</b>
          {line && <div className={s['mem-summary']}>{line}</div>}
          {!open && <Chips names={rest} />}
        </div>
        <span className={s['mem-acts']}>
          <Copy text={'$state:' + path} what="its path" />
          <Change leaf={leaf} path={path} tree={tree} />
        </span>
        <span className={cx(s['mem-chev'], open && s.open)}>
          <Icon name="right" />
        </span>
      </div>
      {open && (
        <div className={s['mem-grid']}>
          {parts.map(([k, v]) => (
            <GridRow key={k} name={k} child={v} path={`${path}/${k}`} owner={leaf} tree={tree} />
          ))}
        </div>
      )}
    </div>
  );
}

/** A folder at the top of the memory, shown as its JSON with "raw". */
export function Folder({
  name,
  count,
  size,
  when,
  raw,
  tree,
  children,
}: {
  name: string;
  count: number;
  size: string;
  when: number;
  raw?: unknown;
  tree: TreeState;
  children: () => ReactNode;
}) {
  const [asJson, setAsJson] = useState(false);
  const open = tree.open.has(name);
  return (
    <section className={cx(s['mem-folder'], open && s.open)}>
      <div className={s['mem-folder-head']} onClick={() => tree.toggle(name)}>
        <span className={cx(s['mem-chev'], open && s.open)}>
          <Icon name="right" />
        </span>
        <b>{name}</b>
        <span className={css('slate-text')}>{` · ${count} ${count === 1 ? 'item' : 'items'}`}</span>
        <span style={{ flex: 1 }} />
        {open && raw !== undefined && (
          <button
            type="button"
            className={cx(s['mem-raw-btn'], asJson && s.on)}
            onClick={(e) => {
              e.stopPropagation();
              setAsJson(!asJson);
            }}
          >
            raw
          </button>
        )}
        <span className={css('slate-text')}>{[size, when ? ago(when) : ''].filter(Boolean).join(' · ')}</span>
      </div>
      {open &&
        (asJson && raw !== undefined ? <pre className={s['mem-raw']}>{JSON.stringify(raw, null, 2)}</pre> : children())}
    </section>
  );
}

/** A record of the catalogue: every file of the module, by its 12-character id. */
export function RecordCard({ record, tree }: { record: AssetRecord; tree: TreeState }) {
  const path = '/assets/' + record.id;
  const open = tree.open.has(path);
  const line = String(record.prompt || record.visual || record.shows || record.filename || record.made || '');
  const fields = Object.keys(record).filter((k) => !['id', 'name', 'item', 'entry'].includes(k));
  return (
    <div className={cx(s['mem-card'], open && s.open)}>
      <div className={s['mem-card-head']} onClick={() => tree.toggle(path)}>
        <Thumb record={record} />
        <div className={s['mem-card-text']}>
          <div>
            <b>{record.name}</b>
            <span className={s['mem-id']}>{record.id}</span>
          </div>
          {line && <div className={s['mem-summary']}>{line}</div>}
          {!open && <Chips names={fields} />}
        </div>
        <span className={s['mem-acts']}>
          <Copy text={`$state:/assets/${record.id}/url`} what="its reference" />
        </span>
        <span className={cx(s['mem-chev'], open && s.open)}>
          <Icon name="right" />
        </span>
      </div>
      {open && (
        <div className={s['mem-grid']}>
          {fields.map((k) => (
            <GridRow key={k} name={k} child={record[k]} path={`${path}/${k}`} owner={null} tree={tree} />
          ))}
        </div>
      )}
    </div>
  );
}

export type { Memory };
