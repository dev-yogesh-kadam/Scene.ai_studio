// What floats over the board and follows the camera: the minimap (a mark for each frame, and the box of what is in
// view), and the way back to the work, shown only while none of it is in sight.

import { useLayoutEffect, useRef, useSyncExternalStore } from 'react';
import { Icon } from '../../../common/components/Icon/Icon';
import { cx } from '../../../common/cx';
import type { Camera } from './camera';
import { FRAME, bounds, type Key } from './geometry';
import s from './Board.module.css';
import { classesOf } from '../../../common/cx';
import css0 from './Shared.module.css';
const css = classesOf(css0);

type Mark = { key: Key; x: number; y: number; h: number };

/** The minimap: the marks, in canvas units inside one layer scaled to fit; a moving camera only changes the layer's
 *  scale and the box of what is in view. */
export function Minimap({ camera, marks, selected }: { camera: Camera; marks: Mark[]; selected: Set<number> }) {
  const layer = useRef<HTMLDivElement>(null);
  const view = useRef<HTMLElement>(null);
  const many = marks.length >= 2;
  useLayoutEffect(() => {
    if (!many) return;
    const all = bounds(marks);
    const place = () => {
      const seen = camera.seen();
      const left = Math.min(all.x, seen.x);
      const top = Math.min(all.y, seen.y);
      const scale = Math.min(
        120 / (Math.max(all.right, seen.right) - left),
        72 / (Math.max(all.bottom, seen.bottom) - top),
      );
      if (layer.current) layer.current.style.transform = `scale(${scale}) translate(${-left}px, ${-top}px)`;
      if (view.current)
        view.current.style.cssText = `left:${(seen.x - left) * scale}px;top:${(seen.y - top) * scale}px;width:${(seen.right - seen.x) * scale}px;height:${(seen.bottom - seen.y) * scale}px`;
    };
    place();
    return camera.subscribe(place);
  }, [camera, marks, many]);
  if (!many) return null;
  return (
    <div className={s.minimap} aria-hidden="true">
      <div ref={layer} className={s['minimap-layer']}>
        {marks.map((b) => (
          <i
            key={String(b.key)}
            className={selected.has(b.key as number) ? s.on : ''}
            style={{ left: b.x, top: b.y, width: FRAME, height: b.h }}
          />
        ))}
      </div>
      <b ref={view} />
    </div>
  );
}

/** The way back, shown only while none of the work is in sight. The board can be scrolled away from it without end. */
export function Lost({ camera, any, onBack }: { camera: Camera; any: boolean; onBack: () => void }) {
  const away = useSyncExternalStore(camera.subscribe, () => any && !camera.inSight());
  if (!away) return null;
  return (
    <div className={css(cx('float', s['canvas-lost']))}>
      <button type="button" className="btn small quiet" title="Show all your work (1)" onClick={onBack}>
        <Icon name="target" />
        Back to your work
      </button>
    </div>
  );
}
