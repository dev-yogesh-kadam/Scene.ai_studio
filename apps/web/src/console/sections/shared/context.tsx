// What the console's sections share while it is open: who is signed in, the period, each section's filters, and how a
// section is drawn again (its queries asked again) or another one opened with some of its filters changed.

import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query';
import { createContext, useContext, useMemo, useRef, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router';

export type ConsoleUser = {
  id: number;
  name: string;
  email: string;
  role: string;
  role_label?: string;
  sections?: string[];
  studio: { port: number };
};

type Filters = Record<string, Record<string, string | number>>;

const FIRST_FILTERS: Filters = {
  users: { q: '', show: '' },
  jobs: { status: 'active', q: '', offset: 0 },
  library: { kind: '', q: '', owner: '', project: '', offset: 0 },
  credits: { reason: '', q: '' },
  audit: { q: '' },
  workflows: { show: '' },
  agent: { days: 7 },
  projects: { q: '' },
  moderation: { show: 'review' },
  sessions: { q: '', state: '' },
};

type Console = {
  user: ConsoleUser;
  days: number;
  setDays: (days: number) => void;
  filters: Filters;
  setFilters: (section: string, changes: Record<string, string | number>) => void;
  refresh: () => Promise<void>;
  go: (section: string, changes?: Record<string, string | number>) => void;
};

const Context = createContext<Console | null>(null);

export function useConsole() {
  const value = useContext(Context);
  if (!value) throw new Error('useConsole outside the console');
  return value;
}

export function ConsoleProvider({ user, children }: { user: ConsoleUser; children: ReactNode }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [days, setDays] = useState(30);
  const [filters, set] = useState(FIRST_FILTERS);
  const value = useMemo<Console>(
    () => ({
      user,
      days,
      setDays,
      filters,
      setFilters: (section, changes) => set((was) => ({ ...was, [section]: { ...was[section], ...changes } })),
      refresh: () => client.invalidateQueries({ queryKey: ['console'] }),
      go: (section, changes) => {
        if (changes) set((was) => ({ ...was, [section]: { ...was[section], ...changes } }));
        void navigate('/' + section);
      },
    }),
    [user, days, filters, client, navigate],
  );
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

/** A section's filters, kept while the console is open, and how to change them. */
export function useFilters<T extends Record<string, string | number>>(section: string) {
  const { filters, setFilters } = useConsole();
  return [
    filters[section] as T,
    (changes: Partial<T>) => setFilters(section, changes as Record<string, string | number>),
  ] as const;
}

/** What a section shows: asked again whenever the section is drawn again, the last answer staying until the new one. */
export function useSection<T>(section: string, key: unknown[], ask: () => Promise<T>) {
  return useQuery({ queryKey: ['console', section, ...key], queryFn: ask, placeholderData: keepPreviousData });
}

/** Runs `work`, then says the result on a line of the form: {text, ok} for its notice. */
export function useNotice() {
  const [notice, setNotice] = useState<{ text: string; ok: boolean }>({ text: '', ok: false });
  const busy = useRef(false);
  const run = async (work: () => Promise<string | void>) => {
    if (busy.current) return;
    busy.current = true;
    try {
      const said = await work();
      if (said) setNotice({ text: said, ok: true });
    } catch (e) {
      setNotice({ text: (e as Error).message, ok: false });
    }
    busy.current = false;
  };
  return { notice, setNotice, run };
}
