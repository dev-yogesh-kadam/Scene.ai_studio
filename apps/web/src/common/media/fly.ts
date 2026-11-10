// The viewer grows out of the picture that was clicked and goes back into it when it closes, so it is always clear
// where it came from. The last press anywhere is remembered to find that picture.

import { Spring } from '../motion/spring';

let pressed: Element | null = null;
document.addEventListener('pointerdown', (e) => (pressed = e.target as Element), true);

export type Source = { pic: HTMLImageElement | HTMLVideoElement; w: number; h: number };

/** The picture under the last press: an image or a video shown in what was pressed. */
export function pressedPicture(): Source | null {
  const holder = pressed?.isConnected ? pressed.closest('button, a, [role="button"], [data-picture]') : null;
  const pic: HTMLImageElement | HTMLVideoElement | undefined = holder
    ? holder.getElementsByTagName('img')[0] || holder.getElementsByTagName('video')[0]
    : undefined;
  if (!pic || !pic.getBoundingClientRect().width) return null;
  const size =
    pic instanceof HTMLVideoElement ? [pic.videoWidth, pic.videoHeight] : [pic.naturalWidth, pic.naturalHeight];
  return size[0] && size[1] ? { pic, w: size[0], h: size[1] } : null;
}

/** Where the picture will sit in the viewer: as large as fits, never larger than it is, in the middle. */
function landing(area: HTMLElement, w: number, h: number) {
  const box = area.getBoundingClientRect();
  const pad = parseFloat(getComputedStyle(area).paddingLeft) || 0;
  const scale = Math.min(1, (box.width - pad * 2) / w, (Math.min(box.height, innerHeight) - pad * 2) / h);
  return {
    x: box.left + (box.width - w * scale) / 2,
    y: box.top + (Math.min(box.height, innerHeight) - h * scale) / 2,
    w: w * scale,
    h: h * scale,
  };
}

/** The still flies between the thumbnail and the viewer on one spring, 0 at the thumbnail and 1 in the viewer. Closing
 *  while it is still opening turns it round from where it is. */
export function flyFrom(dialog: HTMLDialogElement, area: HTMLElement, source: Source, flyer: HTMLElement) {
  // A video flies as the frame it is showing.
  if (flyer instanceof HTMLCanvasElement) {
    try {
      flyer.getContext('2d')?.drawImage(source.pic, 0, 0, source.w, source.h);
    } catch {
      return null;
    }
  }
  flyer.hidden = false;
  dialog.toggleAttribute('data-flying', true);
  let from = source.pic.getBoundingClientRect();
  const to = landing(area, source.w, source.h);
  const put = (p: number) => {
    const w = from.width + (to.w - from.width) * p;
    const h = from.height + (to.h - from.height) * p;
    flyer.style.transform = `translate(${from.left + (to.x - from.left) * p}px, ${from.top + (to.y - from.top) * p}px)`;
    flyer.style.width = w + 'px';
    flyer.style.height = h + 'px';
    dialog.style.setProperty('--open', String(Math.max(0, Math.min(1, p))));
  };
  const spring = new Spring(0, put, 0.001);
  spring.to(1, {
    response: 0.42,
    done: () => {
      dialog.toggleAttribute('data-flying', false);
      flyer.hidden = true;
    },
  });
  return {
    back(done: () => void) {
      if (!source.pic.isConnected) return false;
      from = source.pic.getBoundingClientRect(); // it may have moved while the viewer was open
      flyer.hidden = false;
      put(spring.x);
      dialog.toggleAttribute('data-flying', true);
      spring.to(0, { response: 0.36, done });
      return true;
    },
  };
}
