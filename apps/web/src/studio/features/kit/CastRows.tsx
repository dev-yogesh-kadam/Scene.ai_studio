// The cast of a module: its entries, the always-on ones first ("in every shot, in this order"), each with its name,
// type, Always on, what it shows and how it hangs together with the others. An entry is dragged by its grip: it follows
// the pointer, the others slide up or down to show where it will go, and when it is let go the list is drawn in its
// new order with every row gliding from where it was.

import { useLayoutEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import type { CastEntry } from '@scene/shared/api/kit';
import { cx, mergeModules } from '../../../common/cx';
import { Spring, rubberband } from '../../../common/motion/spring';
import { KitThumb, TypeSelect, type KitEntry } from './kit';
import s1 from './Kit.module.css';
import s2 from './Kit2.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared3.module.css';

const s = mergeModules(s1, s2);
const css = classesOf(css0);

/** How an entry hangs together with the others, in a few words: "look of Maya · from sc 3", "2 looks", "mother of Dev". */
function linksLine(entry: CastEntry, entries: CastEntry[]) {
  const byId = new Map(entries.map((e) => [e.id, e]));
  const parts: string[] = [];
  if (entry.look_of && byId.has(entry.look_of))
    parts.push(
      `${entry.type === 'location' ? 'time of day of' : 'look of'} ${byId.get(entry.look_of)!.name}` +
        (entry.from_scene ? ` · from sc ${entry.from_scene}` : ''),
    );
  const looks = entries.filter((e) => e.look_of === entry.id).length;
  if (looks)
    parts.push(
      `${looks} ${entry.type === 'location' ? (looks === 1 ? 'time of day' : 'times of day') : looks === 1 ? 'look' : 'looks'}`,
    );
  if (entry.palette) parts.push('palette');
  const kin =
    (entry.relations || []).filter((r) => byId.has(r.to)).length +
    entries.filter((e) => (e.relations || []).some((r) => r.to === entry.id)).length;
  if (kin) parts.push(`${kin} ${kin === 1 ? 'relative' : 'relatives'}`);
  return parts.join(' · ');
}

type Props = {
  entries: CastEntry[]; // the whole cast
  shown: CastEntry[]; // what the search and the type filter leave
  onChange: (entry: CastEntry, json: Partial<CastEntry>) => void;
  onRemove: (entry: CastEntry) => void;
  onCard: (entry: CastEntry) => void;
  onMove: (entry: CastEntry, before: CastEntry | null) => void;
};

const slide = (row: HTMLElement) => (y: number) => {
  row.style.translate = y ? `0 ${y}px` : '';
};

export function CastRows({ entries, shown, onChange, onRemove, onCard, onMove }: Props) {
  const rows = useRef(new Map<number, HTMLDivElement>());
  const was = useRef<{ tops: Map<number, number>; moved: number } | null>(null);
  const [lifted, setLifted] = useState<number | null>(null);

  // After a move, every row glides from where it was to its place in the new order.
  useLayoutEffect(() => {
    const before = was.current;
    if (!before) return;
    was.current = null;
    for (const [id, row] of rows.current) {
      const dy = (before.tops.get(id) ?? row.getBoundingClientRect().top) - row.getBoundingClientRect().top;
      if (dy) new Spring(dy, slide(row)).to(0, { response: 0.3, damping: id === before.moved ? 0.8 : 1 });
    }
  }, [shown]);

  const drag = (e: ReactPointerEvent<HTMLSpanElement>, entry: CastEntry) => {
    if (e.button !== 0) return;
    e.preventDefault();
    const grip = e.currentTarget;
    const order = shown.map((x) => x.id).filter((id) => rows.current.has(id));
    const list = order.map((id) => rows.current.get(id)!);
    const index = order.indexOf(entry.id);
    if (index < 0) return;
    const rects = list.map((r) => r.getBoundingClientRect());
    const step =
      rects.length > 1
        ? index < rects.length - 1
          ? rects[index + 1].top - rects[index].top
          : rects[index].top - rects[index - 1].top
        : 0;
    const low = rects[0].top - rects[index].top;
    const high = rects[rects.length - 1].top - rects[index].top;
    const shifts = list.map((r) => new Spring(0, slide(r)));
    const aims = list.map(() => 0);
    const from = e.clientY;
    let to = index;
    grip.setPointerCapture(e.pointerId);
    setLifted(entry.id);
    const onMoveRow = (ev: PointerEvent) => {
      const dy = ev.clientY - from;
      const y = dy < low ? low - rubberband(low - dy, 120) : dy > high ? high + rubberband(dy - high, 120) : dy;
      shifts[index].set(y);
      const middle = rects[index].top + y + rects[index].height / 2;
      to = rects.filter((r, i) => i !== index && r.top + r.height / 2 < middle).length;
      list.forEach((_, i) => {
        if (i === index) return;
        const aim = i > index && i <= to ? -step : i < index && i >= to ? step : 0;
        if (aim !== aims[i]) {
          aims[i] = aim;
          shifts[i].to(aim, { response: 0.3 });
        }
      });
    };
    const end = () => {
      grip.removeEventListener('pointermove', onMoveRow);
      grip.removeEventListener('pointerup', end);
      grip.removeEventListener('pointercancel', end);
      shifts.forEach((x) => x.stop());
      if (to === index) {
        shifts.forEach((x) => x.to(0, { response: 0.3, done: () => setLifted(null) }));
        return;
      }
      setLifted(null);
      // The entry it now goes before: the one shown at that place, or, at the end of what is shown, the one after it.
      const others = shown.filter((x) => x.id !== entry.id);
      const rest = entries.filter((x) => x.id !== entry.id);
      const last = others[others.length - 1];
      const target = others[to] || rest[rest.indexOf(last) + 1] || null;
      was.current = {
        tops: new Map(order.map((id) => [id, rows.current.get(id)!.getBoundingClientRect().top])),
        moved: entry.id,
      };
      list.forEach((r) => slide(r)(0));
      onMove(entry, target);
    };
    grip.addEventListener('pointermove', onMoveRow);
    grip.addEventListener('pointerup', end);
    grip.addEventListener('pointercancel', end);
  };

  const row = (entry: CastEntry) => {
    const links = linksLine(entry, entries);
    return (
      <div
        key={entry.id}
        ref={(node) => {
          if (node) rows.current.set(entry.id, node);
          else rows.current.delete(entry.id);
        }}
        className={cx(
          s['kit-row'],
          !entry.named && s.unnamed,
          !!entry.always && s.always,
          lifted === entry.id && s.lifted,
        )}
      >
        <span
          className={s['kit-grip']}
          title="Drag to change the order"
          aria-hidden="true"
          onPointerDown={(e) => drag(e, entry)}
        >
          ⋮⋮
        </span>
        <span className={cx(s['memory-thumb'], s['kit-thumb'])}>
          <KitThumb entry={entry as KitEntry} />
        </span>
        <div className={s['kit-main']}>
          <div className={s['kit-line']}>
            <input
              key={entry.name}
              className={s['kit-name']}
              defaultValue={entry.name}
              maxLength={60}
              aria-label="Name"
              onBlur={(e) => {
                if (e.target.value.trim() && e.target.value !== entry.name) onChange(entry, { name: e.target.value });
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') e.currentTarget.blur();
              }}
            />
            {!entry.named && (
              <span className={s['kit-flag']} title="The agent will ask who or what this is">
                needs a name
              </span>
            )}
          </div>
          <div className={s['kit-line']}>
            <TypeSelect value={entry.type} onChange={(type) => onChange(entry, { type })} />
            {entry.kind !== 'text' && (
              <label className={s['kit-always']} title="Put it into every shot that has a place for it">
                <input
                  type="checkbox"
                  checked={!!entry.always}
                  onChange={(e) => onChange(entry, { always: e.target.checked })}
                />
                <span>Always on</span>
              </label>
            )}
          </div>
          <button
            type="button"
            className={cx(s['kit-about'], 'small muted')}
            title="What it shows, how to use it, and how it fits with the rest"
            onClick={() => onCard(entry)}
          >
            {entry.use_note ||
              entry.about ||
              (entry.kind === 'image' || entry.kind === 'video' ? 'Being looked at…' : 'Add what it is')}
          </button>
          {links && <div className={cx(s['kit-links-line'], 'small muted')}>{links}</div>}
        </div>
        <button
          className={cx('icon-btn', s['kit-remove'])}
          title="Take it out of the cast"
          aria-label={`Take ${entry.name} out of the cast`}
          onClick={() => onRemove(entry)}
        >
          ×
        </button>
      </div>
    );
  };

  const on = shown.filter((e) => e.always);
  const rest = shown.filter((e) => !e.always);
  return (
    <>
      {on.length > 0 && (
        <div className={s['kit-group']}>
          <h3>
            Always on<span className={css('slate-text')}> · in every shot, in this order</span>
          </h3>
          {on.map(row)}
        </div>
      )}
      {rest.length > 0 && (
        <div className={s['kit-group']}>
          {on.length > 0 && <h3>The rest</h3>}
          {rest.map(row)}
        </div>
      )}
    </>
  );
}
