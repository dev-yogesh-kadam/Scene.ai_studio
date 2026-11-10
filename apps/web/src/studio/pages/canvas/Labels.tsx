// What is drawn behind the frames: the boards left of the shots (NeuralCore by type, the outputs, the final video) with
// their entries' names, all the shots in one board with a line between one shot and the next, the name of each shot
// down its left side (click to rename), and, while a frame is dragged over the gap between two shots, the line that
// says a new shot starts there.

import { memo, useRef, useState } from 'react';
import { Icon } from '../../../common/components/Icon/Icon';
import { cx } from '../../../common/cx';
import { gapLine } from './arrange';
import { FRAME, GAP, LABEL, SLATE, rowName, type Band, type BoardCard, type Row } from './geometry';
import s from './Board.module.css';

type Props = {
  cards: BoardCard[];
  bands: Band[];
  rows: Row[];
  gap: number; // the gap a dragged frame is over, or -1
  onRename: (row: Row, name: string) => void;
};

/** Where the board of shots is across: as wide as the longest shot, the names of the shots inside it. */
export function boardBox(bands: Band[]) {
  const left = -LABEL - GAP / 4;
  const width = Math.max(1, ...bands.map((band) => band.row.keys.length)) * (FRAME + GAP) - left - GAP / 2;
  return { left, width };
}

export const Labels = memo(function Labels({ cards, bands, rows, gap, onRename }: Props) {
  const [naming, setNaming] = useState<number | null>(null); // the id of the row being renamed
  const pad = GAP / 3;
  const last = bands[bands.length - 1];
  const { left, width } = boardBox(bands);
  return (
    <>
      {cards.map((c) => (
        <div key={'card:' + c.label}>
          <div className={s['board-card']} style={{ left: c.x, top: c.y, width: c.w, height: c.h }}>
            <span className={s['board-chip']}>
              <Icon name="grid" />
              {c.label}
              <i>{String(c.count)}</i>
            </span>
          </div>
          {c.names.map((n) => (
            <div
              key={`${n.x}:${n.y}`}
              className={s['board-name']}
              style={{ left: n.x, top: n.y, width: FRAME }}
              title={n.text}
            >
              {n.text}
            </div>
          ))}
        </div>
      ))}
      {last ? (
        <div
          className={cx(s.lane, s['lane-board'])}
          style={{
            left,
            top: bands[0].y - pad,
            width,
            height: last.y + last.h + SLATE + pad - (bands[0].y - pad),
          }}
        />
      ) : null}
      {bands.slice(1).map((band, i) => (
        <div
          key={'line:' + band.row.id}
          className={s['lane-divider']}
          style={{ left: left + GAP / 4, top: (bands[i].y + bands[i].h + SLATE + band.y) / 2, width: width - GAP / 2 }}
        />
      ))}
      {bands.map((band) => (
        <ShotLabel
          key={'label:' + band.row.id}
          band={band}
          name={rowName(rows, band.row)}
          plain={rowName(rows, band.row, true)}
          naming={naming === band.row.id}
          onStart={() => setNaming(band.row.id)}
          onDone={(name) => {
            setNaming(null);
            if (name !== null) onRename(band.row, name);
          }}
        />
      ))}
      {gap >= 0 && bands.length ? (
        <div
          className={s['insert-mark']}
          style={{ left: left + GAP / 4, width: width - GAP / 2, top: gapLine(bands, gap) }}
        >
          <span>New shot here</span>
        </div>
      ) : null}
    </>
  );
});

function ShotLabel({
  band,
  name,
  plain,
  naming,
  onStart,
  onDone,
}: {
  band: Band;
  name: string;
  plain: string; // its usual name: given back as no name
  naming: boolean;
  onStart: () => void;
  onDone: (name: string | null) => void; // null: left as it was
}) {
  const ended = useRef(false); // Enter or Escape ended it: the blur as the box goes changes nothing
  const end = (name: string | null) => {
    if (ended.current) return;
    ended.current = true;
    onDone(name);
  };
  const keep = (typed: string) => end(typed.trim() === plain ? '' : typed.trim());
  return (
    <button
      className={s['shot-label']}
      title="Rename this shot"
      style={{ left: -LABEL, top: band.y, width: LABEL - GAP / 2, height: band.h }}
      onPointerDown={(e) => e.stopPropagation()}
      onClick={() => {
        if (naming) return;
        ended.current = false;
        onStart();
      }}
    >
      {naming ? (
        <input
          type="text"
          className={s['shot-name']}
          maxLength={40}
          defaultValue={name}
          aria-label="Name of the shot"
          ref={(input) => input?.select()}
          onPointerDown={(e) => e.stopPropagation()}
          onBlur={(e) => keep(e.currentTarget.value)}
          onKeyDown={(e) => {
            e.stopPropagation();
            if (e.key === 'Enter') keep(e.currentTarget.value);
            else if (e.key === 'Escape') end(null);
          }}
        />
      ) : (
        name
      )}
    </button>
  );
}
