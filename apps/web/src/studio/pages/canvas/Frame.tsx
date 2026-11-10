// A frame on the canvas: a finished item at its spot, with its line of facts under it (the slate), "+" to add it to the
// agent's message, its shot's badge and, on the take on top of a stack, the switch between takes. A NeuralCore entry
// that is a file of its own is a frame on its board too (FileFrame).

import { memo, useLayoutEffect, useRef, type PointerEvent as ReactPointerEvent } from 'react';
import { Icon } from '../../../common/components/Icon/Icon';
import { Still } from '../../../common/components/Still';
import { cx } from '../../../common/cx';
import { Spring } from '../../../common/motion/spring';
import type { Item } from '../../../common/media/item';
import { STACK_SHOWN, shotNumber, take, type Key, type KitEntry, type Spot, type Stack } from './geometry';
import s from './Frame.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared3.module.css';
import css1 from '../../features/agent/Composer.module.css';
import css2 from '../../features/agent/Markdown.module.css';
import css3 from '../../features/agent/Results.module.css';
const css = classesOf(css0, css1, css2, css3);

type Props = {
  item: Item;
  spot: Spot;
  at: { x: number; y: number }; // where it is drawn: its spot, or where it is being dragged
  boardName?: string;
  selected: boolean;
  lifted: boolean;
  spotlight: number; // changes each time the conversation points at it: the ring shows again
  glide: number; // changes after a drop: a frame that changed place slides there from where it was
  dropped: boolean; // one of the frames dropped: it lands with a little give
  onGrab: (e: ReactPointerEvent, id: number) => void;
  onOpen: (item: Item) => void;
  onAttach: (item: Item) => void;
  onPickTake: (stack: Stack, key: Key) => void;
};

/** After a drop, a frame that changed place slides from where it was to its new spot, so the eye can follow it. */
export function useGlide(at: { x: number; y: number }, glide: number, dropped: boolean) {
  const node = useRef<HTMLDivElement>(null);
  const was = useRef({ at, glide });
  useLayoutEffect(() => {
    const before = was.current;
    was.current = { at, glide };
    const dx = before.at.x - at.x;
    const dy = before.at.y - at.y;
    const el = node.current;
    if (!el || before.glide === glide || (!dx && !dy)) return;
    const spring = new Spring(
      1,
      (t) => {
        el.style.translate = t ? `${dx * t}px ${dy * t}px` : '';
      },
      0.002,
    ).to(0, { response: 0.35, damping: dropped ? 0.8 : 1 });
    return () => spring.stop();
  }, [at, glide, dropped]);
  return node;
}

export const Frame = memo(function Frame({
  item,
  spot,
  at,
  boardName,
  selected,
  lifted,
  spotlight,
  glide,
  dropped,
  onGrab,
  onOpen,
  onAttach,
  onPickTake,
}: Props) {
  const node = useGlide(at, glide, dropped);
  const c = item.context ?? {};
  const n = shotNumber(item.settings);
  const depth = spot.depth ?? 0;
  const stop = (e: { stopPropagation: () => void }) => e.stopPropagation();
  return (
    <div
      ref={node}
      data-picture
      className={cx(
        s.frame,
        selected && s.selected,
        lifted && s.lifted,
        depth > 0 && s['stack-behind'],
        depth > STACK_SHOWN && s['stack-buried'],
        spot.board && s['on-board'],
      )}
      style={{
        left: at.x,
        top: at.y,
        zIndex: spot.stack ? STACK_SHOWN + 1 - Math.min(depth, STACK_SHOWN) : undefined,
      }}
      title={depth ? `${item.name}: an earlier take. Click to put it on top.` : item.name}
      onPointerDown={(e) => onGrab(e, item.id)}
      onDoubleClick={() => onOpen(item)}
    >
      <div className={cx(s.shot, s.gate)} style={{ height: spot.h }}>
        <Still
          url={`/api/library/${item.id}/file`}
          kind={item.kind}
          name={item.name}
          width={item.context?.width}
          height={item.context?.height}
        />
      </div>
      <button
        type="button"
        className={s['frame-attach']}
        title="Add to chat"
        aria-label={`Add ${item.name} to the chat`}
        onPointerDown={stop}
        onDoubleClick={stop}
        onClick={(e) => {
          e.stopPropagation();
          onAttach(item);
        }}
      >
        <Icon name="plus" />
      </button>
      {n ? (
        <span className={s['shot-badge']} title={`Shot ${n} of the story`}>
          {`Shot ${n}`}
        </span>
      ) : null}
      {!depth && spot.stack && spot.stack.members.length > 1 ? (
        <TakeSwitch stack={spot.stack} id={item.id} onPick={onPickTake} />
      ) : null}
      {/* a new ring each time the conversation points at it, so it shows again when it is already there */}
      {spotlight ? <span key={spotlight} className={s.spotlight} aria-hidden="true" /> : null}
      <div className={s.slate}>
        <b>{spot.board ? boardName || item.name : take(spot)}</b>
        <span>{c.width ? `${item.kind} · ${c.width}×${c.height}` : item.name}</span>
      </div>
    </div>
  );
});

/** "‹ 2 / 3 ›" on the take on top of a stack: the earlier take, which one this is, the later take. Takes count from
 *  the oldest, so the newest has the highest number. */
function TakeSwitch({ stack, id, onPick }: { stack: Stack; id: Key; onPick: (stack: Stack, key: Key) => void }) {
  const index = stack.members.indexOf(id); // members are newest first
  const total = stack.members.length;
  const button = (text: string, by: number, hint: string) => (
    <button
      type="button"
      className={s['stack-step']}
      title={hint}
      aria-label={hint}
      onPointerDown={(e) => e.stopPropagation()}
      onDoubleClick={(e) => e.stopPropagation()}
      onClick={(e) => {
        e.stopPropagation();
        onPick(stack, stack.members[(index + by + total) % total]);
      }}
    >
      {text}
    </button>
  );
  return (
    <div className={s['stack-switch']} role="group" aria-label="Takes of this shot">
      {button('‹', 1, 'The earlier take')}
      <span>{`${total - index} / ${total}`}</span>
      {button('›', -1, 'The later take')}
    </div>
  );
}

/** A NeuralCore entry that is a file of its own (uploaded, or kept from a reference): a frame on its board. A double
 *  click opens the file. A picture shows itself; a clip, a sound or a script shows what it is. */
export const FileFrame = memo(function FileFrame({ entry, spot }: { entry: KitEntry; spot: Spot }) {
  return (
    <div
      data-picture
      className={cx(s.frame, s['on-board'], s['file-frame'])}
      style={{ left: spot.x, top: spot.y }}
      title={`${entry.name} (NeuralCore)`}
      onDoubleClick={() => window.open(entry.url, '_blank', 'noopener')}
    >
      <div className={s.shot} style={{ height: spot.h }}>
        {entry.kind === 'image' ? (
          <Still url={entry.url ?? ''} kind="image" name={entry.name} />
        ) : (
          <div className={css('sound')}>
            <Icon name={entry.kind === 'video' ? 'video' : entry.kind === 'audio' ? 'audio' : 'book'} />
            <span>{entry.name}</span>
          </div>
        )}
      </div>
      <div className={s.slate}>
        <b>{entry.name}</b>
        <span>{entry.type || ''}</span>
      </div>
    </div>
  );
});
