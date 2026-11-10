// The signed-in user, for every page: who they are, their credits (kept current by the live connection), and signing
// out. A 401 from any call (other than the sign-in's own) means the session ended: back to the sign-in page.

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router';
import type { Me } from '@scene/shared/types/api';
import { api, setOnUnauthorized } from '../common/api';
import { userPrefs } from './userPrefs';

export type Session = {
  user: Me;
  setUser: (update: (user: Me) => Me) => void;
  signOut: () => Promise<void>;
};

const SessionContext = createContext<Session | null>(null);

export function useSession() {
  const session = useContext(SessionContext);
  if (!session) throw new Error('useSession() outside a signed-in page');
  return session;
}

export const useUser = () => useSession().user;

/** Where an admin's browser finds the admin console, a site of its own: the address the studio was told, or its port
 *  on the host the studio was opened at. */
export function consoleAddress(user: Me) {
  return user.console?.url || `${location.protocol}//${location.hostname}:${user.console?.port}`;
}

/** Loads who is signed in, and draws `signedIn` for them or `signedOut` for no one. */
export function SessionGate({
  signedIn,
  signedOut,
}: {
  signedIn: ReactNode;
  signedOut: (onSignedIn: (user: Me) => void) => ReactNode;
}) {
  const [user, setUserState] = useState<Me | null | undefined>(undefined);
  const navigate = useNavigate();

  useEffect(() => {
    let live = true;
    api<Me>('/api/auth/me').then(
      (me) => live && setUserState(me),
      () => live && setUserState(null),
    );
    setOnUnauthorized((path) => {
      if (!path.startsWith('/api/auth/')) setUserState(null);
    });
    // The modules carried over from the classic studio say so with an event (their streamed calls).
    const signedOut = () => setUserState(null);
    window.addEventListener('scene:signed-out', signedOut);
    return () => {
      live = false;
      setOnUnauthorized(null);
      window.removeEventListener('scene:signed-out', signedOut);
    };
  }, []);

  const setUser = useCallback((update: (user: Me) => Me) => setUserState((u) => (u ? update(u) : u)), []);
  const signOut = useCallback(async () => {
    await api('/api/auth/logout', { method: 'POST' }).catch(() => {}); // signed out either way
    void navigate('/', { replace: true });
    setUserState(null);
  }, [navigate]);
  const session = useMemo(() => (user ? { user, setUser, signOut } : null), [user, setUser, signOut]);

  // The user's own choices (the agent's model and permission, the workflows used last...) before any page reads them.
  const [prefsOf, setPrefsOf] = useState<number | null>(null);
  const userId = user?.id ?? null;
  useEffect(() => {
    if (userId == null) return;
    let live = true;
    void userPrefs.load().then(() => live && setPrefsOf(userId));
    return () => {
      live = false;
    };
  }, [userId]);

  if (user === undefined) return null; // not known yet: nothing, as the classic page drew nothing
  if (!session) return <>{signedOut((me) => setUserState(me))}</>;
  if (prefsOf !== session.user.id) return null;
  return <SessionContext.Provider value={session}>{signedIn}</SessionContext.Provider>;
}
