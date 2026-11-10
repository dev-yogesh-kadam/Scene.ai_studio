import { useQueryClient } from '@tanstack/react-query';
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { AppState } from 'react-native';

import { mergeById, mergeList } from '@scene/shared/live/merge';
import { startMonitoring } from '@scene/shared/monitor';
import type { JobsAnswer } from '@scene/shared/types/api';
import { fromLive } from '@/lib/jobs';
import { releases } from '@/lib/whatsNew';
import { useSession } from './useSession';

const LiveContext = createContext(false);
const PING_EVERY = 25_000;

/**
 * A live line to the studio (its /api/events socket, signed in by the session cookie): when a job moves, a result
 * lands or credits change, what it says goes straight into the cached lists, written only where something changed.
 * While it is up the screens do not poll; without it they poll, slowly. It closes while the page is hidden.
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

  // What goes wrong in the phone site, and for some visits how fast it is, told to the studio while someone is signed in.
  useEffect(() => {
    if (status !== 'signedIn' || typeof location === 'undefined') return;
    return startMonitoring({ app: 'phone', build: releases[0]?.version ?? '' });
  }, [status]);

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
        let said: { jobs?: unknown; credits?: number; library_changed?: boolean; plans?: { id: number }[] };
        try {
          said = JSON.parse(String(event.data));
        } catch {
          return;
        }
        if (Array.isArray(said.jobs)) {
          // Where every job stands, put into the list as it is; it is fetched again (at most every 2 s) only for what
          // the message cannot say: the items a job that just finished made, or the list when none was fetched yet.
          const was = queryClient.getQueryData<JobsAnswer>(['jobs']);
          const heard = was ? fromLive(said.jobs as Parameters<typeof fromLive>[0], was) : null;
          if (was && heard) {
            const jobs = mergeList(was.jobs, heard.answer.jobs);
            if (jobs !== was.jobs) queryClient.setQueryData<JobsAnswer>(['jobs'], { ...was, jobs });
          }
          const now = Date.now();
          if ((!heard || heard.missing) && now - lastJobs.current > 2000) {
            lastJobs.current = now;
            void queryClient.invalidateQueries({ queryKey: ['jobs'] });
          }
        }
        if (Array.isArray(said.plans)) {
          // Where the plans the studio carries out stand; the conversation that has one applies it.
          const heard = said.plans;
          const was = queryClient.getQueryData<Map<number, { id: number }>>(['plans']);
          const next = mergeById(was, heard);
          if (next !== was) queryClient.setQueryData(['plans'], next);
        }
        if (typeof said.credits === 'number') {
          queryClient.setQueryData(['credits'], (old: { balance: number; events: unknown[] } | undefined) =>
            old && old.balance !== said.credits ? { ...old, balance: said.credits! } : old,
          );
        }
        if (said.library_changed) {
          for (const key of ['library', 'module', 'module-items', 'projects', 'project'])
            void queryClient.invalidateQueries({ queryKey: [key] });
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

/** Whether the live line is up: screens then do not poll. */
export function useLive() {
  return useContext(LiveContext);
}
