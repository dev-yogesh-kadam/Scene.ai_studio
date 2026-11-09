import { useQueryClient } from '@tanstack/react-query';
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { AppState } from 'react-native';

import { useSession } from './useSession';

const LiveContext = createContext(false);
const PING_EVERY = 25_000;

/**
 * A live line to the studio (its /api/events socket, signed in by the session cookie): when a job moves, a result
 * lands or credits change, the lists refresh at once. While it is up the screens poll rarely; without it they poll as
 * before. It closes while the page is hidden.
 */
export function LiveProvider({ children }: { children: ReactNode }) {
  const { status } = useSession();
  const queryClient = useQueryClient();
  const [connected, setConnected] = useState(false);
  const [active, setActive] = useState(AppState.currentState === 'active');
  const lastJobs = useRef(0);

  useEffect(() => {
    const subscription = AppState.addEventListener('change', (state) => setActive(state === 'active'));
    return () => subscription.remove();
  }, []);

  useEffect(() => {
    if (status !== 'signedIn' || !active || typeof location === 'undefined') return;
    let socket: WebSocket | null = null;
    let ping: ReturnType<typeof setInterval> | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let wait = 2000;
    let closed = false;

    const open = () => {
      socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/events`);
      socket.onopen = () => {
        wait = 2000;
        setConnected(true);
        ping = setInterval(() => socket?.readyState === 1 && socket.send(JSON.stringify({ ping: true })), PING_EVERY);
      };
      socket.onmessage = (event) => {
        let said: { jobs?: unknown; credits?: number; library_changed?: boolean };
        try {
          said = JSON.parse(String(event.data));
        } catch {
          return;
        }
        if (said.jobs) {
          // Progress comes many times a minute: the job list is asked again at most every 2 s.
          const now = Date.now();
          if (now - lastJobs.current > 2000 || said.library_changed) {
            lastJobs.current = now;
            void queryClient.invalidateQueries({ queryKey: ['jobs'] });
          }
        }
        if (typeof said.credits === 'number') {
          queryClient.setQueryData(['credits'], (old: { balance: number; events: unknown[] } | undefined) => (old ? { ...old, balance: said.credits! } : old));
        }
        if (said.library_changed) {
          for (const key of ['library', 'module', 'module-items', 'projects', 'project']) void queryClient.invalidateQueries({ queryKey: [key] });
        }
      };
      socket.onclose = () => {
        setConnected(false);
        if (ping) clearInterval(ping);
        if (!closed) {
          retry = setTimeout(open, wait);
          wait = Math.min(wait * 2, 60_000);
        }
      };
      socket.onerror = () => socket?.close();
    };
    open();
    return () => {
      closed = true;
      if (ping) clearInterval(ping);
      if (retry) clearTimeout(retry);
      socket?.close();
      setConnected(false);
    };
  }, [status, active, queryClient]);

  return <LiveContext.Provider value={connected}>{children}</LiveContext.Provider>;
}

/** Whether the live line is up: screens then poll rarely. */
export function useLive() {
  return useContext(LiveContext);
}
