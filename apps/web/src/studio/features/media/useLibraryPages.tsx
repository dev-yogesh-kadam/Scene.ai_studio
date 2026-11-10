// The library a page at a time for a list that grows as it is scrolled (the Library page, the canvas's drawer): the
// pages so far as one list, and a marker at its end that asks for the next page once it comes near the screen.

import { useInfiniteQuery, type QueryKey } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import { itemsPage, type ItemsFilter } from '@scene/shared/api/items';
import type { Item } from '../../../common/media/item';
import s from './useLibraryPages.module.css';

export const LIBRARY_PAGE = 60;

export function useLibraryPages(key: QueryKey, filter: Omit<ItemsFilter, 'limit'>, enabled = true) {
  const query = useInfiniteQuery({
    queryKey: key,
    queryFn: ({ pageParam }) => itemsPage<Item>({ ...filter, limit: LIBRARY_PAGE }, pageParam),
    initialPageParam: '',
    getNextPageParam: (page) => page.next_cursor || undefined,
    enabled,
  });
  return { ...query, items: query.data?.pages.flatMap((page) => page.items) };
}

/** The nearest box that scrolls, for the marker to be seen in (the page itself when none does). */
function scroller(node: HTMLElement) {
  for (let up = node.parentElement; up; up = up.parentElement) {
    const { overflowY } = getComputedStyle(up);
    if ((overflowY === 'auto' || overflowY === 'scroll') && up.scrollHeight > up.clientHeight) return up;
  }
  return null;
}

/** Put after the list's items: while there are more pages, an empty marker the width of the grid; the next page is
 *  asked for when it comes within a screen of being seen. */
export function LoadMore({ pages }: { pages: ReturnType<typeof useLibraryPages> }) {
  const marker = useRef<HTMLDivElement>(null);
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = pages;
  useEffect(() => {
    const node = marker.current;
    if (!node || !hasNextPage || isFetchingNextPage) return;
    const seen = new IntersectionObserver((entries) => entries.some((e) => e.isIntersecting) && void fetchNextPage(), {
      root: scroller(node),
      rootMargin: '600px 0px',
    });
    seen.observe(node);
    return () => seen.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);
  return hasNextPage ? <div ref={marker} className={s.more} aria-hidden="true" /> : null;
}
