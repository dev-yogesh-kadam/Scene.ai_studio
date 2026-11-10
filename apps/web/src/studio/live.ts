// The live connection (packages/shared/live) for the signed-in studio: what it hears goes into the Query cache (the jobs,
// the render server's state) and the session (the credits); "the library changed" makes the library's queries stale.
// A busy queue says where its jobs stand several times a second: what is heard before the next frame is put in at once,
// and only what changed is written, so a page is drawn again only for a change it shows.

import { notifyManager, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router';
import { startLive, type Live, type LiveMessage } from '@scene/shared/live';
import { batcher, mergeById, mergeList } from '@scene/shared/live/merge';
import { startMonitoring } from '@scene/shared/monitor';
import type { Job } from '@scene/shared/types/api';
import { api } from '../common/api';
import { useSession } from './session';

export type StudioStatus = { online: boolean | null; page?: number };

export const JOBS = ['jobs'] as const;
export const STATUS = ['status'] as const;
export const PLANS = ['plans'] as const; // the plans the studio carries out, as the live connection last said them
/** The build this page runs: its entry file's name, which carries the hash of its content. */
const BUILD = new URL(import.meta.url).pathname.split('/').pop() || 'dev';

const fetchJobs = () => api<{ jobs: Job[] }>('/api/jobs').then((answer) => answer.jobs);

/** This user's jobs, as the live connection last said (or as fetched). */
export function useJobs() {
  return useQuery({ queryKey: JOBS, queryFn: fetchJobs, staleTime: Infinity }).data ?? [];
}

/** Whether the render server answers (null until known), and the version of the page files on the server. */
export function useStatus(): StudioStatus {
  return (
    useQuery<StudioStatus>({ queryKey: STATUS, queryFn: () => ({ online: null }), staleTime: Infinity, enabled: false })
      .data ?? { online: null }
  );
}

/** Runs while the studio is open for a signed-in user. */
export function useStudioLive() {
  const client = useQueryClient();
  const { setUser } = useSession();
  const location = useLocation();
  const live = useRef<Live | null>(null);

  useEffect(() => {
    const setJobs = (jobs: Job[]) => {
      const was = client.getQueryData<Job[]>(JOBS);
      const next = mergeList(was, jobs);
      if (next !== was) client.setQueryData(JOBS, next);
    };
    const heard = (batch: LiveMessage[]) =>
      notifyManager.batch(() => {
        const jobs = batch.findLast((m) => Array.isArray(m.jobs))?.jobs; // each says every job: the last one is enough
        if (jobs) setJobs(jobs as Job[]);
        const plans = batch.flatMap((m) => (Array.isArray(m.plans) ? (m.plans as { id: number }[]) : []));
        if (plans.length) {
          const was = client.getQueryData<Map<number, { id: number }>>(PLANS);
          const next = mergeById(was, plans);
          if (next !== was) client.setQueryData(PLANS, next);
        }
        const credits = batch.findLast((m) => m.credits != null)?.credits;
        if (credits != null) {
          const balance = Number(credits);
          setUser((user) => (user.credits === balance ? user : { ...user, credits: balance }));
        }
        if (batch.some((m) => m.library_changed)) {
          void client.invalidateQueries({ queryKey: ['library'] });
          void client.invalidateQueries({ queryKey: ['projects'] });
        }
      });
    const batch = batcher(heard);
    live.current = startLive({
      onMessage: batch.add,
      pollJobs: () => fetchJobs().then(setJobs),
      pollStatus: () =>
        api<{ online: boolean; page?: number }>('/api/status').then(
          (found) => {
            client.setQueryData<StudioStatus>(STATUS, { online: found.online, page: found.page });
          },
          (error) => {
            client.setQueryData<StudioStatus>(STATUS, (was) => ({ ...was, online: false }));
            throw error;
          },
        ),
      page: () => window.location.pathname.replace(/\/+$/, '') || '/',
    });
    void fetchJobs()
      .then(setJobs)
      .catch(() => {});
    // what goes wrong in the page, and for some pages how fast it is, told to the studio while someone is signed in
    const stopMonitoring = startMonitoring({ app: 'studio', build: BUILD });
    return () => {
      live.current?.stop();
      batch.drop();
      stopMonitoring();
    };
  }, [client, setUser]);

  useEffect(() => {
    live.current?.sayPage();
  }, [location.pathname]);
}
