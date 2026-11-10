// Getting a result out of the studio from the phone's browser: shared through the phone's share sheet (the file
// itself where the browser can, else its link), or downloaded.
import { fileUrl } from '@scene/shared/api/library';
import type { LibraryItem } from '@scene/shared/types/api';

function safeName(item: LibraryItem) {
  const base = item.name.replace(/[^\w\- ]+/g, '').trim().replace(/\s+/g, '-').slice(0, 40) || 'scene';
  return `${base}-${item.id}${item.ext || ''}`;
}

/** Share the file through the phone's share sheet. Says false when the browser can't share files (then download it). */
export async function share(item: LibraryItem): Promise<boolean> {
  if (typeof navigator === 'undefined' || !navigator.share) return false;
  const response = await fetch(fileUrl(item.id), { credentials: 'same-origin' });
  if (!response.ok) throw new Error(`Couldn't fetch the file (${response.status}).`);
  const blob = await response.blob();
  const file = new File([blob], safeName(item), { type: blob.type || 'application/octet-stream' });
  if (navigator.canShare && !navigator.canShare({ files: [file] })) return false;
  try {
    await navigator.share({ files: [file], title: item.name });
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') return true;   // the share sheet was closed: fine
    throw error;
  }
  return true;
}

/** Share a link (to a share page) through the share sheet, or copy it where there is none. Says which. */
export async function shareLink(url: string, title: string): Promise<'shared' | 'copied'> {
  if (typeof navigator !== 'undefined' && navigator.share) {
    try {
      await navigator.share({ url, title });
      return 'shared';
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') return 'shared';
    }
  }
  await navigator.clipboard.writeText(url);
  return 'copied';
}

/** Download the file: the phone puts it in Downloads (and, for pictures and videos, its gallery shows it). */
export function download(item: LibraryItem) {
  const link = document.createElement('a');
  link.href = `${fileUrl(item.id)}?download=1`;
  link.download = safeName(item);
  document.body.appendChild(link);
  link.click();
  link.remove();
}
