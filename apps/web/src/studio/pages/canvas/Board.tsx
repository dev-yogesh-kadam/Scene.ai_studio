// The board: an endless stage the camera looks at, the world on it (the labels behind, the frames of the items, the
// NeuralCore's files and the jobs in progress), and what the pointer does there. The middle button drags the board (it
// carries on when flicked; a finger does too, the left button not), the wheel scrolls it (with Ctrl or ⌘, zooms), files
// dropped on it are uploaded. A frame is selected by a click (Shift adds), dragged into another shot or into the gap
// between two (a new shot there). Only the frames near the part of the world in view are drawn, so a canvas of hundreds
// of shots stays quick.

import {
  memo,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type PointerEvent as ReactPointerEvent,
} from 'react';
import { tracker } from '../../../common/motion/spring';
import type { Item } from '../../../common/media/item';
import { dropInto, gapAt, type Arranged } from './arrange';
import { Camera, track } from './camera';
import { FileFrame, Frame } from './Frame';
import { FRAME, SLATE, SNAP, type Key, type Layout, type Row, type Stack } from './geometry';
import { JobFrame } from './JobFrame';
import { Labels } from './Labels';
import s from './Board.module.css';

const TILE = 512; // the drawn part of the world changes when the view crosses a tile of this many canvas units

type Drag = { ids: number[]; dx: number; dy: number; gap: number };

type Props = {
  camera: Camera;
  arranged: Arranged;
  items: Item[];
  selected: Set<number>;
  spotlight: { id: number; n: number };
  agentJobs: Set<string>;
  admin: boolean;
  onSelect: (next: Set<number>) => void;
  onLayout: (next: Layout) => void;
  onRename: (row: Row, name: string) => void;
  onPickTake: (stack: Stack, key: Key) => void;
  onClickFrame: (item: Item) => boolean; // true when the click was taken (a frame was asked for)
  onOpen: (item: Item) => void;
  onAttach: (item: Item) => void;
  onDragging: (dragging: boolean) => void;
  onFiles: (files: File[]) => void;
  onDropping: (over: boolean) => void;
};

/** The part of the world drawn: what is in view and most of a screen around it, out to whole tiles, so the frames are
 *  drawn again only when the view crosses into another tile. */
function useDrawn(camera: Camera) {
  const key = useSyncExternalStore(camera.subscribe, () => {
    const seen = camera.seen(0.75);
    return [
      Math.floor(seen.x / TILE) * TILE,
      Math.floor(seen.y / TILE) * TILE,
      Math.ceil(seen.right / TILE) * TILE,
      Math.ceil(seen.bottom / TILE) * TILE,
    ].join(':');
  });
  const [x, y, right, bottom] = key.split(':').map(Number);
  return { x, y, right, bottom };
}

export const Board = memo(function Board(props: Props) {
  const { camera, arranged, items, selected, spotlight, agentJobs, admin } = props;
  const stage = useRef<HTMLDivElement>(null);
  const world = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [glide, setGlide] = useState({ n: 0, dropped: new Set<number>() });
  const [panning, setPanning] = useState(false);
  const latest = useRef(props);
  useLayoutEffect(() => {
    latest.current = props;
  });

  useLayoutEffect(() => {
    camera.attach(stage.current, world.current);
    return () => camera.attach(null, null);
  }, [camera]);

  // The wheel scrolls the board up and down (with Shift, sideways); with Ctrl or ⌘ it zooms where the pointer is, a
  // mouse's notch a step, a pinch (which comes with Ctrl) smoothly. Not passive: the page must not scroll.
  useEffect(() => {
    const node = stage.current;
    if (!node) return;
    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      camera.stop();
      if (e.ctrlKey || e.metaKey) {
        const step = Math.max(-1, Math.min(1, e.deltaY / 100)) * 0.15; // a notch is about 100: 15% a notch
        return camera.zoomAt(e.clientX, e.clientY, camera.cam.k * Math.exp(-step));
      }
      if (e.shiftKey && !e.deltaX) return camera.moveTo(camera.cam.x - e.deltaY, camera.cam.y);
      camera.moveTo(camera.cam.x - e.deltaX, camera.cam.y - e.deltaY);
    };
    node.addEventListener('wheel', wheel, { passive: false });
    return () => node.removeEventListener('wheel', wheel);
  }, [camera]);

  // The middle button (the wheel pressed) drags the board, from anywhere on it, over a frame too; so does a finger on a
  // touch screen. The left button does not move it: a click on the empty board clears the selection.
  const pan = (e: ReactPointerEvent) => {
    if (e.button !== 0 && e.button !== 1) return;
    const middle = e.button === 1;
    if (!middle && e.pointerType === 'mouse') {
      if (latest.current.selected.size) latest.current.onSelect(new Set());
      return;
    }
    camera.stop();
    const from = { x: e.clientX, y: e.clientY, cx: camera.cam.x, cy: camera.cam.y };
    const edge = camera.limits();
    const speed = tracker();
    speed.add(e.clientX, e.clientY);
    let moved = false;
    setPanning(true);
    track(
      (ev) => {
        speed.add(ev.clientX, ev.clientY);
        moved = moved || Math.abs(ev.clientX - from.x) + Math.abs(ev.clientY - from.y) > 3;
        let x = from.cx + ev.clientX - from.x;
        let y = from.cy + ev.clientY - from.y;
        if (edge) {
          x = Camera.soft(x, edge.minX, edge.maxX, edge.w);
          y = Camera.soft(y, edge.minY, edge.maxY, edge.h);
        }
        camera.moveTo(x, y);
      },
      () => {
        setPanning(false);
        if (moved) camera.throwWith(speed.velocity());
        else if (!middle && latest.current.selected.size) latest.current.onSelect(new Set());
      },
    );
  };

  // A frame pressed: selected (Shift adds or takes away), then, if the pointer moves, dragged with the others selected.
  const grab = useCallback(
    (e: ReactPointerEvent, id: number) => {
      if (e.button !== 0) return;
      e.stopPropagation();
      const now = latest.current;
      const chosen = new Set(now.selected);
      if (e.shiftKey) {
        if (chosen.has(id)) chosen.delete(id);
        else chosen.add(id);
      } else if (!chosen.has(id)) {
        chosen.clear();
        chosen.add(id);
      }
      now.onSelect(chosen);
      camera.stop();
      const { spots, bands, layout } = now.arranged;
      const from = { x: e.clientX, y: e.clientY };
      const k = camera.cam.k;
      // What is on a board stays there: it can be selected, opened and added to the chat, not moved into a shot.
      const moving = [...chosen].filter((key) => spots.get(key) && !spots.get(key)!.board);
      const held = spots.get(id);
      // Where the pointer is on the canvas, to tell a drop on a shot from a drop in the gap between two shots.
      const grip = held ? (from.y - e.currentTarget.getBoundingClientRect().top) / k : 0;
      const startY = held ? held.y + grip : 0;
      let moved = false;
      let last: Drag = { ids: moving, dx: 0, dy: 0, gap: -1 };
      track(
        (ev) => {
          const dx = (ev.clientX - from.x) / k;
          const dy = (ev.clientY - from.y) / k;
          if (!moved && Math.abs(dx) + Math.abs(dy) > 3 / k && moving.length) {
            moved = true;
            latest.current.onDragging(true);
          }
          if (!moved) return;
          last = { ids: moving, dx, dy, gap: gapAt(bands, startY + dy) };
          setDrag(last);
        },
        () => {
          const item = latest.current.items.find((i) => i.id === id);
          // A click only selects. While a panel asked for a frame ("From canvas"), the click gives it this frame.
          if (!moved && item && latest.current.onClickFrame(item)) return;
          if (!moved && held?.depth && held.stack) return latest.current.onPickTake(held.stack, id); // an earlier take: on top
          if (!moved) return;
          latest.current.onDragging(false);
          setDrag(null);
          if (!held) return;
          // Dropped frames join the shot they were dropped on, at that place in the row; below the last row they start
          // a new shot.
          const x = Math.round((held.x + last.dx) / SNAP) * SNAP;
          const y = Math.round((held.y + last.dy) / SNAP) * SNAP;
          setGlide((g) => ({ n: g.n + 1, dropped: new Set(moving) }));
          latest.current.onLayout(dropInto(layout, bands, moving, { x, middle: y + held.h / 2 }, last.gap));
        },
      );
    },
    [camera],
  );

  const seen = useDrawn(camera);
  const near = (spot: { x: number; y: number; h: number }) =>
    spot.x + FRAME > seen.x && spot.x < seen.right && spot.y + spot.h + SLATE > seen.y && spot.y < seen.bottom;

  const { spots, bands, cards, onBoard, jobs, layout } = arranged;
  const atOf = (id: number, spot: { x: number; y: number }) =>
    drag && drag.ids.includes(id)
      ? { x: Math.round((spot.x + drag.dx) / SNAP) * SNAP, y: Math.round((spot.y + drag.dy) / SNAP) * SNAP }
      : spot;
  return (
    <div
      ref={stage}
      className={s['canvas-stage'] + (panning ? ' ' + s.panning : '')}
      onPointerDown={pan}
      onMouseDown={(e) => {
        if (e.button === 1) e.preventDefault(); // no autoscroll circle under a middle-button drag
      }}
      onDragOver={(e) => {
        if (![...e.dataTransfer.types].includes('Files')) return;
        e.preventDefault();
        props.onDropping(true);
      }}
      onDragLeave={(e) => {
        if (e.target === stage.current) props.onDropping(false);
      }}
      onDrop={(e) => {
        if (!e.dataTransfer.files.length) return;
        e.preventDefault();
        props.onDropping(false);
        props.onFiles([...e.dataTransfer.files]);
      }}
    >
      <div ref={world} className={s['canvas-world']}>
        <div>
          <Labels cards={cards} bands={bands} rows={layout.rows} gap={drag?.gap ?? -1} onRename={props.onRename} />
        </div>
        <div>
          {[...spots.entries()]
            .filter(([key, spot]) => String(key).startsWith('kit:') && spot.entry && near(spot))
            .map(([key, spot]) => (
              <FileFrame key={key} entry={spot.entry!} spot={spot} />
            ))}
        </div>
        <div>
          {items.map((item) => {
            const spot = spots.get(item.id);
            if (!spot) return null;
            const held = selected.has(item.id) || drag?.ids.includes(item.id) || spotlight.id === item.id;
            if (!held && !near(spot)) return null;
            return (
              <Frame
                key={item.id}
                item={item}
                spot={spot}
                at={atOf(item.id, spot)}
                boardName={onBoard.get(item.id)?.name}
                selected={selected.has(item.id)}
                lifted={!!drag?.ids.includes(item.id)}
                spotlight={spotlight.id === item.id ? spotlight.n : 0}
                glide={glide.n}
                dropped={glide.dropped.has(item.id)}
                onGrab={grab}
                onOpen={props.onOpen}
                onAttach={props.onAttach}
                onPickTake={props.onPickTake}
              />
            );
          })}
        </div>
        <div>
          {jobs.map((job) => {
            const spot = spots.get('job:' + job.id);
            return spot && near(spot) ? (
              <JobFrame key={job.id} job={job} spot={spot} byAgent={agentJobs.has(job.id)} admin={admin} />
            ) : null;
          })}
        </div>
      </div>
    </div>
  );
});
