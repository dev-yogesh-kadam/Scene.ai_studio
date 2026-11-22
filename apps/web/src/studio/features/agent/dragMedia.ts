// Dragging a picture or a video of the project (from the conversation, a take, a review) into the message box: it goes
// in as a chip, like "+", never as the browser's own full-size <img> in the text. While dragging, a small thumbnail
// follows the pointer instead of the whole picture.

/** What a drag started in the studio carries: the library id of the item. */
export const ITEM_TYPE = 'application/x-scene-item';

/** The library id in a studio link ("/api/library/12/poster", "…/12/file?download=1"), or null. */
export function libraryIdIn(text: string | null | undefined): number | null {
  const found = /\/api\/library\/(\d+)\/(?:file|poster|frame)\b/.exec(text || '');
  return found ? Number(found[1]) : null;
}

/** The library id a drop carries: its own type first, then a link or a picture's markup. */
export function droppedItemId(data: DataTransfer): number | null {
  const own = Number(data.getData(ITEM_TYPE));
  if (own > 0) return own;
  for (const type of ['text/uri-list', 'text/html', 'text/plain']) {
    const id = libraryIdIn(data.getData(type));
    if (id) return id;
  }
  return null;
}

/** Whether a drag is one the message box takes: a studio item, a file, or a picture or link from a page. */
export function isMediaDrag(data: DataTransfer | null): boolean {
  const types = [...(data?.types || [])];
  return (
    types.includes(ITEM_TYPE) ||
    types.includes('Files') ||
    types.includes('text/uri-list') ||
    types.includes('text/html')
  );
}

const THUMB = 64;

/** A small rounded thumbnail as the drag picture: the dragged picture itself is often the size of the chat. */
function thumbnail(data: DataTransfer, src: string) {
  const frame = document.createElement('div');
  frame.style.cssText =
    `position:fixed;left:-1000px;top:-1000px;width:${THUMB}px;height:${THUMB}px;border-radius:12px;overflow:hidden;` +
    'box-shadow:0 6px 20px rgba(0,0,0,.35);background:#222';
  const img = document.createElement('img');
  img.src = src;
  img.style.cssText = 'width:100%;height:100%;object-fit:cover;display:block';
  frame.appendChild(img);
  document.body.appendChild(frame);
  data.setDragImage(frame, THUMB / 2, THUMB / 2);
  setTimeout(() => frame.remove(), 0);
}

/** dragstart anywhere in the page: a picture or video of the library (or anything marked data-drag-item) carries its
 * id and a small thumbnail. Anything else drags as it always did. */
export function onMediaDragStart(e: DragEvent) {
  const target = e.target instanceof Element ? e.target : null;
  const data = e.dataTransfer;
  if (!target || !data) return;
  const marked = target.closest<HTMLElement>('[data-drag-item]');
  const media = marked ? null : target.closest<HTMLImageElement | HTMLVideoElement>('img, video');
  const id = marked
    ? Number(marked.dataset.dragItem)
    : media
      ? libraryIdIn(
          media instanceof HTMLVideoElement ? media.poster || media.currentSrc : media.currentSrc || media.src,
        )
      : null;
  if (!id) return;
  data.setData(ITEM_TYPE, String(id));
  data.effectAllowed = 'copy';
  thumbnail(data, `/api/library/${id}/poster`);
}
