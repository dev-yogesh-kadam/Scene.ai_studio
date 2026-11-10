// The message box: typed text with chips in it, one per attached item, so the words around a chip say what it is for.
// While the user types, the browser edits the box and React leaves it alone; when something changes its pieces (a chip
// added or taken out, a skill put in, the box emptied) they are read from the box, changed as data, and the box is drawn
// anew from them with the cursor put back. And above it: what is selected on the canvas, offered as one suggestion.

import {
  forwardRef,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react';
import { Icon } from '../../../common/components/Icon/Icon';
import { Still } from '../../../common/components/Still';
import { cx } from '../../../common/cx';
import type { Item } from '../../../common/media/item';
import { cutAt, insertAt, lengthOf, textBefore, tidy, typedOf, type Attached, type Piece } from './messageParts';
import type { Typed } from './types';
import s from './Composer.module.css';

export type BoxHandle = {
  read: () => Typed;
  clear: () => void;
  snapshot: () => Piece[];
  restore: (pieces: unknown) => void;
  focus: () => void;
  contains: (node: Node) => boolean;
  attach: (item: Pick<Item, 'id' | 'name' | 'kind'>) => void;
  setText: (text: string) => void;
  skillHere: (id: string, query: Slash) => void;
  skillFirst: (id: string) => void;
};
export type Slash = { start: number; end: number; query: string };

const isChip = (n: Node): n is HTMLElement => n instanceof HTMLElement && !!n.dataset.id;

/** What is in the box now. A line break the browser made is a new line. */
function piecesOf(root: Node): Piece[] {
  const out: Piece[] = [];
  const walk = (nodes: NodeListOf<ChildNode>) => {
    for (const n of nodes) {
      if (n.nodeType === Node.TEXT_NODE) out.push(n.textContent ?? '');
      else if (isChip(n))
        out.push({ id: Number(n.dataset.id), name: n.dataset.name ?? '', kind: n.dataset.kind ?? 'image' });
      else if (n.nodeName === 'BR') out.push('\n');
      else {
        walk(n.childNodes);
        if (n.nodeName === 'DIV') out.push('\n');
      }
    }
  };
  walk(root.childNodes);
  return tidy(out);
}

/** The place of the cursor in the box, or null when it is elsewhere. */
function caretIn(root: Node) {
  const picked = window.getSelection();
  if (!picked?.rangeCount || !root.contains(picked.anchorNode)) return null;
  const range = picked.getRangeAt(0);
  let count = 0;
  let found: number | null = null;
  const walk = (node: Node) => {
    if (found !== null) return;
    if (node === range.startContainer && node.nodeType === Node.TEXT_NODE) {
      found = count + range.startOffset;
      return;
    }
    if (node.nodeType === Node.TEXT_NODE) {
      count += node.textContent?.length ?? 0;
      return;
    }
    if (isChip(node)) {
      count += 1;
      return;
    }
    if (node.nodeName === 'BR') count += 1;
    node.childNodes.forEach((child, i) => {
      if (found === null && node === range.startContainer && i === range.startOffset) found = count;
      walk(child);
    });
    if (found === null && node === range.startContainer && range.startOffset >= node.childNodes.length) found = count;
  };
  walk(root);
  return found;
}

/** Puts the cursor at this place. */
function placeCaret(root: Node, at: number) {
  let left = at;
  const range = document.createRange();
  for (const [i, n] of [...root.childNodes].entries()) {
    const size = n.nodeType === Node.TEXT_NODE ? (n.textContent?.length ?? 0) : 1;
    if (n.nodeType === Node.TEXT_NODE && left <= size) {
      range.setStart(n, left);
      break;
    }
    if (left <= 0) {
      range.setStart(root, i);
      break;
    }
    left -= size;
    if (i === root.childNodes.length - 1) range.setStart(root, root.childNodes.length);
  }
  range.collapse(true);
  const picked = window.getSelection();
  picked?.removeAllRanges();
  picked?.addRange(range);
}

type Props = {
  placeholder: string;
  waiting: boolean; // it cannot be used now
  onEnter: () => void;
  onKey: (e: ReactKeyboardEvent) => boolean; // true when the key was used (the skill menu's)
  onSlash: (slash: Slash | null) => void;
  onIds: (ids: number[]) => void;
};

export const MessageBox = forwardRef<BoxHandle, Props>(function MessageBox(
  { placeholder, waiting, onEnter, onKey, onSlash, onIds },
  ref,
) {
  const box = useRef<HTMLDivElement>(null);
  const [drawn, setDrawn] = useState<{ pieces: Piece[]; n: number; caret: number | null }>({
    pieces: [],
    n: 0,
    caret: null,
  });
  const caret = useRef<number | null>(null); // where the cursor last was: a click on the canvas takes the focus away
  const now = () => (box.current ? piecesOf(box.current) : []);
  const draw = (pieces: Piece[], at: number | null) => {
    setDrawn((was) => ({ pieces, n: was.n + 1, caret: at }));
    caret.current = at;
    onIds(pieces.filter((p): p is Attached => typeof p !== 'string').map((p) => p.id));
  };
  // Drawn anew: the cursor goes back where it belongs.
  useLayoutEffect(() => {
    if (!drawn.n || drawn.caret === null || !box.current) return;
    box.current.focus();
    placeCaret(box.current, drawn.caret);
  }, [drawn]);
  useLayoutEffect(() => {
    const remember = () => {
      const at = box.current && caretIn(box.current);
      if (at !== null && at !== undefined) caret.current = at;
    };
    document.addEventListener('selectionchange', remember);
    return () => document.removeEventListener('selectionchange', remember);
  }, []);

  const removeChip = (id: number) => {
    const pieces = now().filter((p) => typeof p === 'string' || p.id !== id);
    draw(tidy(pieces), lengthOf(pieces));
  };
  useImperativeHandle(ref, () => ({
    read: () => typedOf(now()),
    clear: () => draw([], null),
    snapshot: now,
    restore: (pieces) => draw(pieces as Piece[], lengthOf(pieces as Piece[])),
    focus: () => box.current?.focus(),
    contains: (node) => !!box.current?.contains(node),
    attach: (item) => {
      const pieces = now();
      if (pieces.some((p) => typeof p !== 'string' && p.id === item.id)) return;
      const at = caret.current ?? lengthOf(pieces);
      draw(insertAt(pieces, at, [{ id: item.id, name: item.name, kind: item.kind }, ' ']), at + 2);
    },
    setText: (text) => draw([text], text.length),
    // Put "/<id> " where the "/name" being typed is. Straight after a file a space goes in, so the command stands alone.
    skillHere: (id, at) => {
      const pieces = now();
      const before = textBefore(pieces, at.end);
      const glued = !!before && at.start === before.start && before.after !== undefined;
      const tag = (glued ? ' ' : '') + '/' + id + ' ';
      draw(insertAt(cutAt(pieces, at.start, at.end), at.start, [tag]), at.start + tag.length);
    },
    // Put "/<id> " at the very start of the message, where the agent reads it.
    skillFirst: (id) => {
      const pieces = now();
      const first = typeof pieces[0] === 'string' ? pieces[0].replace(/^\s*\/[a-z0-9-]*\s*/i, '') : null;
      const tag = '/' + id + ' ';
      draw(tidy([tag, ...(first !== null ? [first, ...pieces.slice(1)] : pieces)]), tag.length);
    },
  }));

  /** The "/name" just before the cursor, while it is being typed. */
  const slashNow = (): Slash | null => {
    if (!box.current) return null;
    const pieces = piecesOf(box.current);
    const at = caretIn(box.current);
    const before = at === null ? null : textBefore(pieces, at);
    const m = before && /(?:^|\s)\/([a-z0-9-]{0,60})$/i.exec(before.text);
    return m && at !== null ? { start: at - m[1].length - 1, end: at, query: m[1].toLowerCase() } : null;
  };
  return (
    <div
      key={drawn.n}
      ref={box}
      className={s['agent-input']}
      contentEditable={!waiting}
      suppressContentEditableWarning
      role="textbox"
      aria-multiline="true"
      aria-label="Message"
      data-placeholder={placeholder}
      onKeyDown={(e) => {
        if (onKey(e) || e.key !== 'Enter') return;
        e.preventDefault();
        if (e.shiftKey) document.execCommand('insertLineBreak');
        else onEnter();
      }}
      onInput={() => {
        onSlash(slashNow());
        if (box.current)
          onIds(
            piecesOf(box.current)
              .filter((p): p is Attached => typeof p !== 'string')
              .map((p) => p.id),
          );
      }}
      onPaste={(e) => {
        e.preventDefault(); // only the words of what is pasted, never its markup
        document.execCommand('insertText', false, e.clipboardData.getData('text/plain'));
      }}
    >
      {drawn.pieces.map((p, i) =>
        typeof p === 'string' ? (
          p
        ) : (
          <span
            key={i}
            className={s.attach}
            contentEditable={false}
            data-id={p.id}
            data-name={p.name}
            data-kind={p.kind}
            title={p.name}
          >
            <span className={s['attach-thumb']}>
              <Still url={`/api/library/${p.id}/file`} kind={p.kind} />
            </span>
            <span className={s['attach-name']}>{p.name}</span>
            <button
              type="button"
              className={s['attach-drop']}
              title="Remove"
              aria-label={`Remove ${p.name}`}
              tabIndex={-1}
              onClick={() => removeChip(p.id)}
            >
              ×
            </button>
          </span>
        ),
      )}
    </div>
  );
});

/** What is selected on the canvas, offered as one suggestion: it is not part of the message until it is clicked. */
export function Suggest({ list, hidden, onUse }: { list: Item[]; hidden: boolean; onUse: () => void }) {
  return (
    <button
      type="button"
      className={cx(s['agent-suggest'], (hidden || !list.length) && 'hidden')}
      title={'Add to the message: ' + list.map((i) => i.name).join(', ')}
      onClick={onUse}
    >
      <Icon name="plus" />
      <span className={s['agent-suggest-thumbs']}>
        {list.slice(0, 3).map((item) => (
          <span key={item.id} className={s['attach-thumb']}>
            <Still url={`/api/library/${item.id}/file`} kind={item.kind} />
          </span>
        ))}
      </span>
      <span>{list.length === 1 ? `Use “${list[0].name}”` : `Use ${list.length} selected`}</span>
    </button>
  );
}
