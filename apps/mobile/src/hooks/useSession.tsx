import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import * as auth from '@scene/shared/api/auth';
import { ApiError, setOnUnauthorized } from '@scene/shared/api/client';
import type { User } from '@scene/shared/types/api';

type Session = {
  status: 'loading' | 'signedOut' | 'signedIn';
  user: User | null;
  signIn: (email: string, password: string, code?: string) => Promise<void>;
  signOut: () => Promise<void>;
};

const SessionContext = createContext<Session | null>(null);

/** Who is signed in. The studio's session cookie is the sign-in: signed in to the studio, signed in here, and back. */
export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Session['status']>('loading');
  const [user, setUser] = useState<User | null>(null);

  const forget = useCallback(() => {
    setUser(null);
    setStatus('signedOut');
  }, []);

  useEffect(() => {
    auth
      .me()
      .then((found) => {
        setUser(found);
        setStatus('signedIn');
      })
      .catch((error) => {
        // Offline or the studio is down: not known to be signed out, so the screens show the error instead.
        if (error instanceof ApiError && error.status === 401) forget();
        else setStatus('signedIn');
      });
  }, [forget]);

  useEffect(() => {
    setOnUnauthorized(forget);
    return () => setOnUnauthorized(null);
  }, [forget]);

  const signIn = useCallback(async (email: string, password: string, code?: string) => {
    setUser(await auth.login(email, password, code));
    setStatus('signedIn');
  }, []);

  const signOut = useCallback(async () => {
    await auth.logout().catch(() => undefined);
    forget();
  }, [forget]);

  const value = useMemo(() => ({ status, user, signIn, signOut }), [status, user, signIn, signOut]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const session = useContext(SessionContext);
  if (!session) throw new Error('useSession must be used inside SessionProvider');
  return session;
}
