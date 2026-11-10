// The bar over the selection: open, re-run, reuse the seed, download, keep in the NeuralCore. It is drawn again only
// when the selection changes; while the board moves (every frame of a pan or a glide) it is only moved.

import { useLayoutEffect, useRef } from 'react';
import { cx } from '../../../common/cx';
import { seedOf, type Item } from '../../../common/media/item';
import { KIT } from '../../words';
import type { Camera } from './camera';
import { bounds, type Spot } from './geometry';
import s from './Toolbar.module.css';
import { classesOf } from '../../../common/cx';
import css0 from '../../../common/components/Shared3.module.css';
import css1 from './Shared.module.css';
const css = classesOf(css0, css1);

type Props = {
  camera: Camera;
  chosen: Item[]; // the selected items that are drawn
  spots: Map<number | string, Spot>;
  project: number;
  hidden: boolean; // while frames are dragged
  onOpen: (item: Item) => void;
  onRerun: (item: Item) => void;
  onReuseSeed: (item: Item) => void;
  onDownload: (items: Item[]) => void;
  onKeep: (item: Item) => void;
};

const made = (item: Item) => !/^(edit|upload)\//.test(item.workflow);

export function Selection({ camera, chosen, spots, project, hidden, ...act }: Props) {
  const bar = useRef<HTMLDivElement>(null);
  const placed = chosen.map((i) => spots.get(i.id)).filter((spot) => spot !== undefined);
  const area = placed.length ? bounds(placed) : null;
  const ax = area ? area.x : 0;
  const ay = area ? area.y : 0;
  const shown = !!area && !hidden;
  useLayoutEffect(() => {
    if (!shown) return;
    const place = () => {
      const { x, y, k } = camera.cam;
      if (!bar.current) return;
      bar.current.style.left = Math.max(8, x + ax * k) + 'px';
      bar.current.style.top = Math.max(56, y + ay * k - 48) + 'px';
    };
    place();
    return camera.subscribe(place);
  }, [camera, ax, ay, shown]);
  if (!shown) return null;
  const one = chosen.length === 1 ? chosen[0] : null;
  const seed = one ? seedOf(one) : null;
  return (
    <div ref={bar} className={css(cx('float', s['canvas-context']))}>
      {!one && <span className={css('slate-text')}>{`${chosen.length} selected`}</span>}
      {one && (
        <button className="btn small quiet" onClick={() => act.onOpen(one)}>
          Open
        </button>
      )}
      {one && made(one) && (
        <button className="btn small quiet" title="Open Create with the same settings" onClick={() => act.onRerun(one)}>
          Re-run
        </button>
      )}
      {one && made(one) && seed != null && (
        <button
          className="btn small quiet"
          title={`Seed ${seed}: open Create with the same settings and this seed, to make the same picture with a change (Draft to Final, a word of the prompt)`}
          onClick={() => act.onReuseSeed(one)}
        >
          Reuse seed
        </button>
      )}
      {one && seed != null && <span className={css('slate-text small')}>{`Seed ${seed}`}</span>}
      <button className="btn small quiet" title="Download (D)" onClick={() => act.onDownload(chosen)}>
        {one ? 'Download' : `Download ${chosen.length}`}
      </button>
      {one && project ? (
        <button
          className="btn small quiet"
          title={`Keep it in this project's ${KIT} under a name`}
          onClick={() => act.onKeep(one)}
        >
          {`Add to ${KIT}`}
        </button>
      ) : null}
    </div>
  );
}
