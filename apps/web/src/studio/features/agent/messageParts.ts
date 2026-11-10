// The message box's content as data: pieces of text and attached items. Each piece is one thing the box draws; a place
// in the message is counted in characters, an item counting as one.

import type { Part, Typed } from './types';

export type Attached = { id: number; name: string; kind: string };
export type Piece = string | Attached;

const isText = (p: Piece): p is string => typeof p === 'string';
const size = (p: Piece) => (isText(p) ? p.length : 1);

/** Text beside text is one piece, and empty text goes. */
export function tidy(pieces: Piece[]) {
  const out: Piece[] = [];
  for (const p of pieces) {
    if (isText(p) && !p) continue;
    const last = out[out.length - 1];
    if (isText(p) && last !== undefined && isText(last)) out[out.length - 1] = last + p;
    else out.push(p);
  }
  return out;
}

export const lengthOf = (pieces: Piece[]) => pieces.reduce((n, p) => n + size(p), 0);

/** The pieces with `added` put in at this place. */
export function insertAt(pieces: Piece[], at: number, added: Piece[]) {
  const out: Piece[] = [];
  let left = at;
  let done = false;
  for (const p of pieces) {
    if (!done && left <= size(p) && (isText(p) || left === 0)) {
      if (isText(p)) out.push(p.slice(0, left), ...added, p.slice(left));
      else out.push(...added, p);
      done = true;
    } else {
      out.push(p);
      if (!done) left -= size(p);
    }
  }
  if (!done) out.push(...added);
  return tidy(out);
}

/** The pieces with the characters between two places taken out, in the text piece they are in. */
export function cutAt(pieces: Piece[], from: number, to: number) {
  const out: Piece[] = [];
  let at = 0;
  for (const p of pieces) {
    const end = at + size(p);
    if (isText(p) && from >= at && to <= end) out.push(p.slice(0, from - at) + p.slice(to - at));
    else out.push(p);
    at = end;
  }
  return tidy(out);
}

/** The text of the piece the place is in, up to the place; and where that piece starts. */
export function textBefore(pieces: Piece[], at: number) {
  let start = 0;
  for (const [i, p] of pieces.entries()) {
    const end = start + size(p);
    if (isText(p) && at >= start && at <= end) return { text: p.slice(0, at - start), start, after: pieces[i - 1] };
    start = end;
  }
  return null;
}

const NBSP = /\u00a0/g;
const words = (text: string) =>
  text
    .replace(NBSP, ' ')
    .replace(/[ \t]+/g, ' ')
    .trim();

/** The message as it is sent: each item becomes its tag (@1, @2… in the order they appear), and the ids go along in
 *  that order. `shown` is the same with the items' names, for the history the model reads; `parts` is the message as
 *  the conversation shows it: words, and the items as small pictures. */
export function typedOf(pieces: Piece[]): Typed {
  const ids: number[] = [];
  const tag = (p: Attached) => {
    if (!ids.includes(p.id)) ids.push(p.id);
    return '@' + (ids.indexOf(p.id) + 1);
  };
  const text = words(pieces.map((p) => (isText(p) ? p : tag(p))).join(''));
  const shown = words(pieces.map((p) => (isText(p) ? p : `[${p.name}]`)).join(''));
  const parts: Part[] = pieces.map((p) =>
    isText(p) ? { text: p.replace(NBSP, ' ') } : { id: p.id, name: p.name, kind: p.kind || 'image' },
  );
  return { text, shown, ids, parts };
}
