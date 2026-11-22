import { describe, expect, it } from 'vitest';
import { ITEM_TYPE, droppedItemId, libraryIdIn } from './dragMedia';

/** A drop's data, as the browser gives it. */
const drop = (data: Record<string, string>) =>
  ({ getData: (type: string) => data[type] ?? '', types: Object.keys(data) }) as unknown as DataTransfer;

describe('a picture or video dragged into the message box', () => {
  it('is found by its library link', () => {
    expect(libraryIdIn('http://localhost/api/library/42/poster')).toBe(42);
    expect(libraryIdIn('/api/library/7/file?download=1')).toBe(7);
    expect(libraryIdIn('/api/kit/7/file')).toBeNull();
    expect(libraryIdIn('')).toBeNull();
  });

  it('reads its own type first, then a link, then a picture’s markup', () => {
    expect(droppedItemId(drop({ [ITEM_TYPE]: '12', 'text/uri-list': '/api/library/99/file' }))).toBe(12);
    expect(droppedItemId(drop({ 'text/uri-list': 'http://x/api/library/99/file' }))).toBe(99);
    expect(droppedItemId(drop({ 'text/html': '<img src="/api/library/5/poster">' }))).toBe(5);
    expect(droppedItemId(drop({ 'text/plain': 'just words' }))).toBeNull();
  });
});
