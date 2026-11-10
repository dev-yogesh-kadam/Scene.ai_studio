// A picture the server is still making (a video's poster, a keyframe) answers 503 with Retry-After: 1. Its <img> asks
// again once, a second later, with a cache-buster so the browser doesn't reuse the failed answer; then it gives up
// quietly (the alt text, or what the caller shows instead).

import { useEffect, useRef, useState } from 'react';

export const RETRY_AFTER = 1000;

/** The address asked for the second time. */
export const again = (src: string) => src + (src.includes('?') ? '&' : '?') + 'r=1';

/** The src to use and the onError to put on the <img>. `onGiveUp`: called when the second try failed too. */
export function useRetryOnce(src: string, onGiveUp?: () => void) {
  const [tried, setTried] = useState<{ for: string; again: boolean }>({ for: src, again: false });
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );
  const second = tried.for === src && tried.again; // a new address starts over
  const onError = () => {
    if (second) return onGiveUp?.();
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setTried({ for: src, again: true }), RETRY_AFTER);
  };
  return { src: second ? again(src) : src, onError };
}
