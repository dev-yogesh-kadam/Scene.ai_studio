// Links inside the studio may be plain <a href="/library"> (in text the agent wrote, say): a click on one (not with a
// modifier key, not to a file or the API, not to another tab) is a move within the page, not a new load.

import { useEffect } from 'react';
import { useNavigate } from 'react-router';

export function LinkClicks() {
  const navigate = useNavigate();
  useEffect(() => {
    const click = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const link = (e.target as Element | null)?.closest?.('a[href]');
      if (!link || (link as HTMLAnchorElement).target || link.hasAttribute('download')) return;
      const href = link.getAttribute('href') || '';
      if (!href.startsWith('/') || href.startsWith('//') || /^\/(api|assets|v|_app|m)\//.test(href)) return;
      if (/\.[a-z0-9]+$/i.test(href.split('?')[0])) return;
      e.preventDefault();
      void navigate(href);
    };
    document.addEventListener('click', click);
    return () => document.removeEventListener('click', click);
  }, [navigate]);
  return null;
}

/** An address from before (/#/library) is moved to the new one (/library). */
export function oldAddress() {
  if (location.hash.startsWith('#/')) history.replaceState(null, '', location.hash.slice(1));
}
